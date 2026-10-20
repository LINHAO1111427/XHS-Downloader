from __future__ import annotations

import json
import re
import sqlite3
from hashlib import sha256
from contextlib import contextmanager
from pathlib import Path
from time import time
from typing import Iterator
from uuid import uuid4

from knowledge_vector_index import ensure_schema as ensure_vector_schema
from knowledge_vector_index import rank as rank_vectors
from knowledge_vector_index import rebuild as rebuild_vectors
from knowledge_vector_index import upsert_vector


class KnowledgeBaseError(ValueError):
    pass


class KnowledgeEntryNotFound(KnowledgeBaseError):
    pass


class GenerationRunNotFound(KnowledgeBaseError):
    pass


KNOWLEDGE_KINDS = frozenset({"general", "note", "image"})
SEED_ENTRIES = (
    {
        "id": "seed-factual-boundary",
        "kind": "general",
        "title": "真实与合规底线",
        "tags": ["真实", "事实", "合规", "可信"],
        "priority": 100,
        "content": (
            "只使用输入素材中能够确认的事实，不虚构亲身体验、效果、数据、价格或承诺。"
            "不确定的信息应省略或使用审慎表达；用户的明确要求与事实边界优先。"
        ),
    },
    {
        "id": "seed-note-structure",
        "kind": "note",
        "title": "笔记结构与可读性",
        "tags": ["笔记", "结构", "可读性", "正文"],
        "priority": 80,
        "content": (
            "开头尽快交代主题或实际价值，正文用短段落组织具体信息，结尾自然收束。"
            "避免空泛套话、重复结论、过量感叹号和表情堆叠，输出应可直接继续编辑。"
        ),
    },
    {
        "id": "seed-note-title-keywords",
        "kind": "note",
        "title": "标题与关键词",
        "tags": ["标题", "关键词", "搜索", "受众"],
        "priority": 75,
        "content": (
            "标题应直接包含核心对象或主题，并体现读者能获得的具体信息。"
            "关键词自然进入标题和正文，不堆砌热词，不用与内容不符的夸张结论换取点击。"
        ),
    },
    {
        "id": "seed-image-mobile-composition",
        "kind": "image",
        "title": "移动端封面构图",
        "tags": ["封面", "构图", "移动端", "主体", "留白"],
        "priority": 80,
        "content": (
            "主体必须在手机缩略图中仍然清晰可辨，层级明确并保留安全边距。"
            "按用户选择的画幅构图；没有明确要求时，优先适合内容流展示的简洁画面。"
        ),
    },
    {
        "id": "seed-image-reference-safety",
        "kind": "image",
        "title": "参考图一致性与画面安全",
        "tags": ["参考图", "一致性", "水印", "文字", "品牌"],
        "priority": 90,
        "content": (
            "使用参考图时保留可确认的主体特征、产品形态和关键视觉信息，但重新完成构图。"
            "不要添加水印、平台标识、无关品牌、无法辨认的文字或素材中不存在的卖点。"
        ),
    },
)


def _now() -> int:
    return int(time())


def _normalize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in tags:
        tag = str(value).strip()
        if not tag or tag in normalized:
            continue
        if len(tag) > 30:
            raise KnowledgeBaseError("单个标签不能超过 30 个字符")
        normalized.append(tag)
    if len(normalized) > 20:
        raise KnowledgeBaseError("标签不能超过 20 个")
    return normalized


def _validate_entry(
    kind: str,
    title: str,
    content: str,
    tags: list[str],
    priority: int,
) -> tuple[str, str, str, list[str], int]:
    kind = kind.strip().lower()
    title = title.strip()
    content = content.strip()
    if kind not in KNOWLEDGE_KINDS:
        raise KnowledgeBaseError("知识类型必须是 general、note 或 image")
    if not title or len(title) > 120:
        raise KnowledgeBaseError("标题长度必须为 1 到 120 个字符")
    if not content or len(content) > 8_000:
        raise KnowledgeBaseError("内容长度必须为 1 到 8000 个字符")
    if not 0 <= priority <= 100:
        raise KnowledgeBaseError("优先级必须在 0 到 100 之间")
    return kind, title, content, _normalize_tags(tags), priority


def _search_terms(value: str) -> set[str]:
    terms: set[str] = set()
    for token in re.findall(r"[a-z0-9][a-z0-9_-]+|[\u4e00-\u9fff]+", value.casefold()):
        if len(token) <= 8:
            terms.add(token)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token) and len(token) > 1:
            terms.update(token[index : index + 2] for index in range(len(token) - 1))
    return terms


CREATION_QUERIES = {
    "note": "爆款笔记拆解 标题 点击 首句 情绪 痛点 人货场 正文",
    "image": "生图 封面 构图 场景 真实感 随拍 光线 产品一致性",
}


def _knowledge_excerpt(content: str, query: str, budget: int) -> str:
    # Imported course chunks often start with provenance and YAML, not the lesson.
    cleaned = re.sub(r"(?ms)^---\s*\n.*?\n---\s*(?:\n|$)", "", content)
    cleaned = "\n".join(line for line in cleaned.splitlines() if not re.match(
        r"^(来源：|课程章节：|原始页面：|读取范围：|##?\s*\d\d:|> 本稿)", line
    )).strip()
    if len(cleaned) <= budget:
        return cleaned
    # Preserve verbatim, query-relevant sentence windows instead of only the opening.
    sentences = re.split(r"(?<=[。！？\n])", cleaned)
    windows, current = [], ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > max(120, budget // 2):
            windows.append(current.strip())
            current = ""
        current += sentence
    if current.strip():
        windows.append(current.strip())
    terms = _search_terms(query)
    ranked = sorted(enumerate(windows), key=lambda item: (
        -sum(term in item[1].casefold() for term in terms), item[0]
    ))
    chosen, remaining = [], max(0, budget - 5)
    for index, window in ranked[:2]:
        excerpt = window[:remaining]
        if excerpt:
            chosen.append((index, excerpt))
            remaining -= len(excerpt) + 3
        if remaining <= 0:
            break
    return "\n…\n".join(text for _, text in sorted(chosen)) + "…"


class KnowledgeBase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS knowledge_entries (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL CHECK (kind IN ('general', 'note', 'image')),
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    priority INTEGER NOT NULL DEFAULT 50 CHECK (priority BETWEEN 0 AND 100),
                    active INTEGER NOT NULL DEFAULT 1,
                    origin TEXT NOT NULL DEFAULT 'manual',
                    created_by TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    use_count INTEGER NOT NULL DEFAULT 0,
                    last_used_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS knowledge_entries_kind_active
                ON knowledge_entries(kind, active);

                CREATE TABLE IF NOT EXISTS generation_runs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    generated_image INTEGER NOT NULL DEFAULT 0,
                    source_text TEXT NOT NULL,
                    instructions TEXT NOT NULL,
                    output_text TEXT NOT NULL,
                    image_paths TEXT NOT NULL DEFAULT '[]',
                    knowledge_ids TEXT NOT NULL DEFAULT '[]',
                    model TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
                    feedback TEXT NOT NULL DEFAULT '',
                    reusable_lesson TEXT NOT NULL DEFAULT '',
                    feedback_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS generation_runs_user_created
                ON generation_runs(user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS generation_records (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT '',
                    generated_image INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    schema_version INTEGER NOT NULL DEFAULT 2
                );
                CREATE INDEX IF NOT EXISTS generation_records_user_created
                ON generation_records(user_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS generation_inputs (
                    record_id TEXT PRIMARY KEY REFERENCES generation_records(id) ON DELETE CASCADE,
                    source_text TEXT NOT NULL DEFAULT '',
                    instructions TEXT NOT NULL DEFAULT '',
                    request_payload TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS generation_outputs (
                    record_id TEXT PRIMARY KEY REFERENCES generation_records(id) ON DELETE CASCADE,
                    output_text TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS generation_assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT NOT NULL REFERENCES generation_records(id) ON DELETE CASCADE,
                    asset_type TEXT NOT NULL DEFAULT 'image',
                    path TEXT NOT NULL,
                    position INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(record_id, path)
                );
                CREATE INDEX IF NOT EXISTS generation_assets_record
                ON generation_assets(record_id, position);
                CREATE TABLE IF NOT EXISTS generation_references (
                    record_id TEXT NOT NULL REFERENCES generation_records(id) ON DELETE CASCADE,
                    reference_type TEXT NOT NULL CHECK (reference_type IN ('knowledge', 'corpus')),
                    reference_id TEXT NOT NULL,
                    PRIMARY KEY(record_id, reference_type, reference_id)
                );
                CREATE TABLE IF NOT EXISTS generation_feedback (
                    record_id TEXT PRIMARY KEY REFERENCES generation_records(id) ON DELETE CASCADE,
                    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
                    feedback TEXT NOT NULL DEFAULT '',
                    reusable_lesson TEXT NOT NULL DEFAULT '',
                    feedback_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS knowledge_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS corpus_entries (
                    id TEXT PRIMARY KEY,
                    source_name TEXT NOT NULL,
                    record_number INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    source_url TEXT NOT NULL DEFAULT '',
                    product_url TEXT NOT NULL DEFAULT '',
                    add_to_cart_24h INTEGER,
                    followers_text TEXT NOT NULL DEFAULT '',
                    sales_text TEXT NOT NULL DEFAULT '',
                    image_paths TEXT NOT NULL DEFAULT '[]',
                    source_digest TEXT NOT NULL DEFAULT '',
                    imported_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    use_count INTEGER NOT NULL DEFAULT 0,
                    last_used_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS corpus_entries_cart
                ON corpus_entries(add_to_cart_24h DESC);
                """
            )
            ensure_vector_schema(connection)
            run_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(generation_runs)")
            }
            if "request_payload" not in run_columns:
                connection.execute(
                    "ALTER TABLE generation_runs "
                    "ADD COLUMN request_payload TEXT NOT NULL DEFAULT '{}'"
                )
            if "corpus_ids" not in run_columns:
                connection.execute(
                    "ALTER TABLE generation_runs "
                    "ADD COLUMN corpus_ids TEXT NOT NULL DEFAULT '[]'"
                )
            self._migrate_generation_runs(connection)
            now = _now()
            for entry in SEED_ENTRIES:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO knowledge_entries(
                        id, kind, title, content, tags, priority, active, origin,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, 'seed', ?, ?)
                    """,
                    (
                        entry["id"],
                        entry["kind"],
                        entry["title"],
                        entry["content"],
                        json.dumps(entry["tags"], ensure_ascii=False),
                        entry["priority"],
                        now,
                        now,
                    ),
                )
            rebuild_vectors(connection, only_missing=True)
            connection.commit()

    @staticmethod
    def _migrate_generation_runs(connection: sqlite3.Connection) -> None:
        """Backfill the normalized history tables while retaining the legacy table for compatibility."""
        rows = connection.execute("SELECT * FROM generation_runs").fetchall()
        for row in rows:
            record_id = str(row["id"])
            now = int(row["created_at"])
            connection.execute(
                """
                INSERT OR IGNORE INTO generation_records(
                    id, user_id, mode, model, generated_image, created_at, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, 2)
                """,
                (record_id, row["user_id"], row["mode"], row["model"], row["generated_image"], now),
            )
            request_payload = row["request_payload"] or "{}"
            connection.execute(
                """
                INSERT OR IGNORE INTO generation_inputs(record_id, source_text, instructions, request_payload)
                VALUES (?, ?, ?, ?)
                """,
                (record_id, row["source_text"], row["instructions"], request_payload),
            )
            connection.execute(
                "INSERT OR IGNORE INTO generation_outputs(record_id, output_text) VALUES (?, ?)",
                (record_id, row["output_text"]),
            )
            try:
                image_paths = json.loads(row["image_paths"] or "[]")
            except (TypeError, json.JSONDecodeError):
                image_paths = []
            if isinstance(image_paths, list):
                for position, path in enumerate(image_paths):
                    if str(path).strip():
                        connection.execute(
                            "INSERT OR IGNORE INTO generation_assets(record_id, asset_type, path, position) VALUES (?, 'image', ?, ?)",
                            (record_id, str(path), position),
                        )
            for field, reference_type in (("knowledge_ids", "knowledge"), ("corpus_ids", "corpus")):
                try:
                    references = json.loads(row[field] or "[]")
                except (TypeError, json.JSONDecodeError):
                    references = []
                if isinstance(references, list):
                    for reference_id in references:
                        if str(reference_id).strip():
                            connection.execute(
                                "INSERT OR IGNORE INTO generation_references(record_id, reference_type, reference_id) VALUES (?, ?, ?)",
                                (record_id, reference_type, str(reference_id)),
                            )
            if row["rating"] is not None or row["feedback"] or row["reusable_lesson"]:
                connection.execute(
                    "INSERT OR IGNORE INTO generation_feedback(record_id, rating, feedback, reusable_lesson, feedback_at) VALUES (?, ?, ?, ?, ?)",
                    (record_id, row["rating"], row["feedback"], row["reusable_lesson"], row["feedback_at"]),
                )
        connection.execute(
            "INSERT OR REPLACE INTO knowledge_schema_migrations(version, applied_at) VALUES (2, ?)",
            (_now(),),
        )

    @staticmethod
    def _write_normalized_run(
        connection: sqlite3.Connection,
        run_id: str,
        user_id: str,
        mode: str,
        generated_image: bool,
        source_text: str,
        instructions: str,
        output_text: str,
        image_paths: list[str],
        knowledge_ids: list[str],
        model: str,
        request_payload: dict,
        corpus_ids: list[str],
        created_at: int,
    ) -> None:
        connection.execute(
            "INSERT OR REPLACE INTO generation_records(id,user_id,mode,model,generated_image,created_at,schema_version) VALUES (?, ?, ?, ?, ?, ?, 2)",
            (run_id, user_id, mode, model, int(generated_image), created_at),
        )
        connection.execute(
            "INSERT OR REPLACE INTO generation_inputs(record_id,source_text,instructions,request_payload) VALUES (?, ?, ?, ?)",
            (run_id, source_text, instructions, json.dumps(request_payload or {}, ensure_ascii=False)),
        )
        connection.execute(
            "INSERT OR REPLACE INTO generation_outputs(record_id,output_text) VALUES (?, ?)",
            (run_id, output_text),
        )
        connection.execute("DELETE FROM generation_assets WHERE record_id=?", (run_id,))
        for position, path in enumerate(image_paths):
            if str(path).strip():
                connection.execute(
                    "INSERT OR IGNORE INTO generation_assets(record_id,asset_type,path,position) VALUES (?, 'image', ?, ?)",
                    (run_id, str(path), position),
                )
        connection.execute("DELETE FROM generation_references WHERE record_id=?", (run_id,))
        for reference_type, references in (("knowledge", knowledge_ids), ("corpus", corpus_ids)):
            for reference_id in dict.fromkeys(references):
                if str(reference_id).strip():
                    connection.execute(
                        "INSERT OR IGNORE INTO generation_references(record_id,reference_type,reference_id) VALUES (?, ?, ?)",
                        (run_id, reference_type, str(reference_id)),
                    )

    def stats(self) -> dict:
        with self._connection() as connection:
            entries = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN active = 1 THEN 1 ELSE 0 END) AS active,
                       SUM(use_count) AS uses
                FROM knowledge_entries
                """
            ).fetchone()
            runs = connection.execute(
                "SELECT COUNT(*) AS total FROM generation_records"
            ).fetchone()
            rated = connection.execute(
                "SELECT COUNT(*) AS total FROM generation_feedback WHERE rating IS NOT NULL"
            ).fetchone()
            corpus = connection.execute(
                "SELECT COUNT(*) AS total FROM corpus_entries"
            ).fetchone()
            vectors = connection.execute(
                "SELECT COUNT(*) AS total FROM knowledge_vectors"
            ).fetchone()
            migration = connection.execute(
                "SELECT MAX(version) AS version FROM knowledge_schema_migrations"
            ).fetchone()
        return {
            "entries": int(entries["total"] or 0),
            "active_entries": int(entries["active"] or 0),
            "uses": int(entries["uses"] or 0),
            "generation_runs": int(runs["total"] or 0),
            "normalized_generation_runs": int(runs["total"] or 0),
            "history_schema_version": int(migration["version"] or 1),
            "rated_runs": int(rated["total"] or 0),
            "corpus_entries": int(corpus["total"] or 0),
            "vector_entries": int(vectors["total"] or 0),
            "vector_version": 1,
        }

    def import_document(self, filename: str, data: bytes, kind: str, created_by: str) -> dict:
        """Import exported knowledge as bounded, attributable, deduplicated chunks."""
        filename = Path(filename.replace("\\", "/")).name
        suffix = Path(filename).suffix.lower()
        if suffix not in {".txt", ".md", ".json"}:
            raise KnowledgeBaseError("请导入 UTF-8 编码的 TXT、Markdown 或 JSON 文档")
        if len(data) > 1024 * 1024:
            raise KnowledgeBaseError("文档请控制在 1 MB 内")
        text = data.decode("utf-8-sig").strip()
        documents = []
        if suffix == ".json":
            payload = json.loads(text)
            entries = payload.get("entries") if isinstance(payload, dict) else payload
            if not isinstance(entries, list):
                raise KnowledgeBaseError('JSON 应为 [{"title":"标题","content":"正文"}] 或包含 entries 数组')
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("content"), str):
                    raise KnowledgeBaseError("JSON 每条知识需要字符串 content 字段")
                title = entry.get("title", Path(filename).stem)
                if not isinstance(title, str):
                    raise KnowledgeBaseError("JSON 标题应为字符串")
                documents.append((title.strip() or Path(filename).stem, entry["content"].strip()))
        else:
            documents.append((Path(filename).stem, text))
        prepared = []
        now = _now()
        for title, content in documents:
            if not content:
                continue
            # Paragraph boundaries are preferred; long single paragraphs are also bounded.
            chunks, chunk = [], ""
            for paragraph in content.split("\n\n"):
                for offset in range(0, len(paragraph), 3500):
                    part = paragraph[offset:offset + 3500]
                    if len(chunk) + len(part) + 2 > 3500:
                        chunks.append(chunk)
                        chunk = ""
                    chunk = (chunk + "\n\n" + part).strip()
            if chunk:
                chunks.append(chunk)
            for index, chunk in enumerate(chunks):
                heading = f"{title[:90]} · {index + 1}/{len(chunks)}"
                _validate_entry(kind, heading, chunk, ["导入知识", "IMA"], 70)
                digest = sha256((kind + "\0" + chunk).encode()).hexdigest()
                prepared.append(("document-" + digest, kind, heading, chunk,
                    json.dumps(["导入知识", "IMA"], ensure_ascii=False), 70, "document:" + filename,
                    created_by, now, now))
        if not prepared or len(prepared) > 300:
            raise KnowledgeBaseError("文档内容为空或超过 300 个知识片段，请分批导入")
        with self._connection() as connection:
            before = connection.total_changes
            connection.executemany(
                """INSERT OR IGNORE INTO knowledge_entries
                (id, kind, title, content, tags, priority, origin, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", prepared)
            inserted = connection.total_changes - before
            rebuild_vectors(connection, only_missing=True)
            connection.commit()
        return {"imported": inserted, "duplicates": len(prepared) - inserted,
                "source": filename, "stats": self.stats()}

    def list_entries(
        self,
        query: str = "",
        kind: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        if kind is not None and kind not in KNOWLEDGE_KINDS:
            raise KnowledgeBaseError("知识类型不存在")
        clauses: list[str] = []
        values: list[object] = []
        if kind:
            clauses.append("kind = ?")
            values.append(kind)
        if query.strip():
            clauses.append("(title LIKE ? OR content LIKE ? OR tags LIKE ?)")
            pattern = f"%{query.strip()}%"
            values.extend((pattern, pattern, pattern))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(max(1, min(limit, 200)))
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM knowledge_entries
                {where}
                ORDER BY active DESC, priority DESC, updated_at DESC
                LIMIT ?
                """,
                values,
            ).fetchall()
        return [self._entry_payload(row) for row in rows]

    def create_entry(
        self,
        kind: str,
        title: str,
        content: str,
        tags: list[str],
        priority: int,
        created_by: str | None,
        *,
        active: bool = True,
        origin: str = "manual",
    ) -> dict:
        kind, title, content, tags, priority = _validate_entry(
            kind, title, content, tags, priority
        )
        entry_id = uuid4().hex
        now = _now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_entries(
                    id, kind, title, content, tags, priority, active, origin,
                    created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    kind,
                    title,
                    content,
                    json.dumps(tags, ensure_ascii=False),
                    priority,
                    int(active),
                    origin,
                    created_by,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM knowledge_entries WHERE id = ?", (entry_id,)
            ).fetchone()
            if row["active"]:
                upsert_vector(connection, row)
            connection.commit()
        return self._entry_payload(row)

    def update_entry(
        self,
        entry_id: str,
        kind: str,
        title: str,
        content: str,
        tags: list[str],
        priority: int,
        active: bool,
    ) -> dict:
        kind, title, content, tags, priority = _validate_entry(
            kind, title, content, tags, priority
        )
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE knowledge_entries
                SET kind = ?, title = ?, content = ?, tags = ?, priority = ?,
                    active = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    kind,
                    title,
                    content,
                    json.dumps(tags, ensure_ascii=False),
                    priority,
                    int(active),
                    _now(),
                    entry_id,
                ),
            )
            if not cursor.rowcount:
                raise KnowledgeEntryNotFound("知识条目不存在")
            row = connection.execute(
                "SELECT * FROM knowledge_entries WHERE id = ?", (entry_id,)
            ).fetchone()
            if row["active"]:
                upsert_vector(connection, row)
            else:
                connection.execute("DELETE FROM knowledge_vectors WHERE entry_id=?", (entry_id,))
            connection.commit()
        return self._entry_payload(row)

    def delete_entry(self, entry_id: str) -> None:
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM knowledge_entries WHERE id = ?", (entry_id,)
            )
            if not cursor.rowcount:
                raise KnowledgeEntryNotFound("知识条目不存在")
            connection.commit()

    def import_corpus(self, export_path: Path) -> dict:
        export_path = export_path.resolve()
        try:
            raw = export_path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise KnowledgeBaseError(f"无法读取爆款素材库：{error}") from error
        source_name = str(payload.get("title") or export_path.stem).strip()
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list):
            raise KnowledgeBaseError("爆款素材库缺少 entries 列表")
        digest = sha256(raw).hexdigest()
        now = _now()
        prepared: list[tuple] = []
        for item in raw_entries:
            if not isinstance(item, dict) or item.get("type") != "product":
                continue
            paragraphs = item.get("paragraphs")
            content = "\n".join(
                str(value).strip()
                for value in paragraphs
                if str(value).strip()
            ) if isinstance(paragraphs, list) else ""
            if not content:
                continue
            record_id = str(item.get("record_id") or "").strip()
            if not record_id:
                record_id = sha256(
                    f"{item.get('number')}:{item.get('title')}".encode("utf-8")
                ).hexdigest()[:24]
            highlights = item.get("highlights")
            highlight_text = " ".join(
                str(value) for value in highlights
            ) if isinstance(highlights, list) else ""
            tags = list(dict.fromkeys(re.findall(r"【([^】]+)】", highlight_text)))
            product_urls = item.get("product_urls")
            product_url = next(
                (str(value).strip() for value in product_urls if str(value).strip()),
                "",
            ) if isinstance(product_urls, list) else ""
            image_items = item.get("images")
            image_paths = [
                str(image.get("local_path", "")).strip()
                for image in image_items
                if isinstance(image, dict) and str(image.get("local_path", "")).strip()
            ] if isinstance(image_items, list) else []
            cart = item.get("add_to_cart_24h")
            prepared.append(
                (
                    f"feishu-{record_id}",
                    source_name,
                    int(item.get("number") or 0),
                    str(item.get("title") or item.get("name") or "未命名素材").strip(),
                    str(item.get("name") or item.get("title") or "未命名商品").strip(),
                    content,
                    json.dumps(tags, ensure_ascii=False),
                    str(item.get("source") or "").strip(),
                    product_url,
                    int(cart) if isinstance(cart, (int, float)) else None,
                    str(item.get("followers_as_written") or "").strip(),
                    str(item.get("sales_as_written") or "").strip(),
                    json.dumps(image_paths, ensure_ascii=False),
                    digest,
                    now,
                    now,
                )
            )
        if not prepared:
            raise KnowledgeBaseError("爆款素材库中没有可导入的商品记录")
        with self._connection() as connection:
            connection.executemany(
                """
                INSERT INTO corpus_entries(
                    id, source_name, record_number, title, product_name, content,
                    tags, source_url, product_url, add_to_cart_24h,
                    followers_text, sales_text, image_paths, source_digest,
                    imported_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source_name = excluded.source_name,
                    record_number = excluded.record_number,
                    title = excluded.title,
                    product_name = excluded.product_name,
                    content = excluded.content,
                    tags = excluded.tags,
                    source_url = excluded.source_url,
                    product_url = excluded.product_url,
                    add_to_cart_24h = excluded.add_to_cart_24h,
                    followers_text = excluded.followers_text,
                    sales_text = excluded.sales_text,
                    image_paths = excluded.image_paths,
                    source_digest = excluded.source_digest,
                    imported_at = excluded.imported_at,
                    updated_at = excluded.updated_at
                """,
                prepared,
            )
            connection.commit()
        return {
            "source": source_name,
            "path": str(export_path),
            "entries": len(prepared),
            "digest": digest,
            "imported_at": now,
        }

    def list_corpus(
        self,
        query: str = "",
        limit: int = 30,
        offset: int = 0,
    ) -> dict:
        values: list[object] = []
        where = ""
        if query.strip():
            pattern = f"%{query.strip()}%"
            where = "WHERE title LIKE ? OR product_name LIKE ? OR content LIKE ? OR tags LIKE ?"
            values.extend((pattern, pattern, pattern, pattern))
        with self._connection() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) AS total FROM corpus_entries {where}",
                values,
            ).fetchone()
            rows = connection.execute(
                f"""
                SELECT * FROM corpus_entries
                {where}
                ORDER BY COALESCE(add_to_cart_24h, -1) DESC, record_number ASC
                LIMIT ? OFFSET ?
                """,
                (*values, max(1, min(limit, 100)), max(0, offset)),
            ).fetchall()
        return {
            "items": [self._corpus_payload(row, summary=True) for row in rows],
            "total": int(total["total"] or 0),
        }

    def get_corpus_entry(self, entry_id: str) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM corpus_entries WHERE id = ?", (entry_id,)
            ).fetchone()
        if not row:
            raise KnowledgeEntryNotFound("爆款素材不存在")
        return self._corpus_payload(row, summary=False)

    def retrieve_corpus(self, query: str, limit: int = 3) -> list[dict]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM corpus_entries").fetchall()
        terms = _search_terms(query)
        ranked: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            name = str(row["product_name"]).casefold()
            tags = str(row["tags"]).casefold()
            searchable = f"{row['title']} {name} {tags} {row['content']}".casefold()
            matches = sum(1 for term in terms if term in searchable)
            name_matches = sum(1 for term in terms if term in name)
            tag_matches = sum(1 for term in terms if term in tags)
            popularity = min(int(row["add_to_cart_24h"] or 0), 10_000) / 10_000
            score = matches + name_matches * 2 + tag_matches + popularity
            if not terms or matches:
                ranked.append((score, row))
        ranked.sort(
            key=lambda item: (item[0], int(item[1]["add_to_cart_24h"] or 0)),
            reverse=True,
        )
        selected = [row for _, row in ranked[: max(1, min(limit, 6))]]
        if selected:
            ids = [str(row["id"]) for row in selected]
            placeholders = ",".join("?" for _ in ids)
            with self._connection() as connection:
                connection.execute(
                    f"""
                    UPDATE corpus_entries
                    SET use_count = use_count + 1, last_used_at = ?
                    WHERE id IN ({placeholders})
                    """,
                    (_now(), *ids),
                )
                connection.commit()
        return [self._corpus_payload(row, summary=False) for row in selected]

    @staticmethod
    def corpus_context(entries: list[dict], max_chars: int = 7_000) -> str:
        if not entries:
            return ""
        parts = [
            "爆款素材库参考（仅提炼选题、场景、成交结构和素材方法；"
            "不得复制原文，不得把案例价格、销量、功效或用户经历写成当前产品事实）："
        ]
        for entry in entries:
            section = f"[案例] {entry['product_name']}\n{entry['content']}"
            if len("\n\n".join(parts + [section])) > max_chars:
                remaining = max_chars - len("\n\n".join(parts)) - 2
                if remaining > 300:
                    parts.append(section[:remaining])
                break
            parts.append(section)
        return "\n\n".join(parts)

    def retrieve(
        self,
        query: str,
        kinds: set[str],
        limit: int = 6,
    ) -> list[dict]:
        selected_kinds = kinds & KNOWLEDGE_KINDS
        if not selected_kinds:
            return []
        placeholders = ",".join("?" for _ in selected_kinds)
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM knowledge_entries
                WHERE active = 1 AND kind IN ({placeholders})
                """,
                tuple(sorted(selected_kinds)),
            ).fetchall()
            vector_scores = rank_vectors(connection, query, selected_kinds, limit=50)
        terms = _search_terms(query)
        ranked: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            title = str(row["title"]).casefold()
            searchable = f"{title} {row['tags']} {row['content']}".casefold()
            matches = sum(1 for term in terms if term in searchable)
            title_matches = sum(1 for term in terms if term in title)
            kind_bonus = 1.5 if row["kind"] != "general" else 1.0
            semantic = max(0.0, float(vector_scores.get(str(row["id"]), 0.0)))
            score = int(row["priority"]) / 100 + kind_bonus + matches + title_matches + semantic * 4.0
            ranked.append((score, row))
        ranked.sort(
            key=lambda item: (item[0], item[1]["priority"], item[1]["updated_at"]),
            reverse=True,
        )
        return [self._entry_payload(row) for _, row in ranked[: max(1, min(limit, 12))]]

    def retrieve_for_creation(self, query: str, kinds: set[str], limit: int = 6) -> list[dict]:
        """Reserve room for product relevance AND reusable writing/photo lessons."""
        limit = max(1, min(limit, 12))
        selected_kinds = kinds & KNOWLEDGE_KINDS
        if not selected_kinds:
            return []
        # Explicit, persistent user requirements must not lose to keyword matches.
        # Read on each request so edits and disabling take effect immediately.
        placeholders = ",".join("?" for _ in selected_kinds)
        with self._connection() as connection:
            required = connection.execute(
                f"""SELECT * FROM knowledge_entries
                    WHERE active=1 AND origin='user_requirement' AND kind IN ({placeholders})
                    ORDER BY priority DESC, updated_at DESC, id ASC LIMIT ?""",
                (*sorted(selected_kinds), limit),
            ).fetchall()
        selected = [self._entry_payload(row) for row in required]
        if len(selected) == limit:
            return selected
        lanes = [self.retrieve(query, kinds, limit=limit)]
        for kind, method_query in CREATION_QUERIES.items():
            if kind in kinds:
                lanes.append(self.retrieve(method_query, {kind}, limit=limit))
        seen = {entry["id"] for entry in selected}
        families = {}
        for entry in selected:
            family = entry["title"].split(" · 分段")[0]
            families[family] = families.get(family, 0) + 1
        for index in range(limit):
            for lane in lanes:
                if index >= len(lane):
                    continue
                entry = lane[index]
                family = entry["title"].split(" · 分段")[0]
                if entry["id"] in seen or families.get(family, 0) >= 2:
                    continue
                seen.add(entry["id"])
                families[family] = families.get(family, 0) + 1
                selected.append(entry)
                if len(selected) == limit:
                    return selected
        return selected

    def context(self, entries: list[dict], max_chars: int = 6_000, *, query: str = "") -> str:
        if not entries:
            return ""
        parts = [
            "本地知识库参考（仅作为创作策略；事实和用户本次明确要求始终优先）："
        ]
        labels = {"general": "通用", "note": "笔记", "image": "图片"}
        used: list[str] = []
        if len(parts[0]) > max_chars:
            return ""
        for index, entry in enumerate(entries):
            remaining = max_chars - len("\n\n".join(parts)) - 2
            allowance = remaining // (len(entries) - index)
            heading = f"[{labels[entry['kind']]}] {entry['title'][:180]}\n"
            if allowance <= len(heading) + 20:
                continue
            strategy_query = CREATION_QUERIES.get(entry["kind"], " ".join(CREATION_QUERIES.values()))
            excerpt = _knowledge_excerpt(entry["content"], query + " " + strategy_query, allowance - len(heading))
            section = heading + excerpt
            if len(section) > remaining:
                break
            parts.append(section)
            used.append(entry["id"])
        self.mark_used(used)
        return "\n\n".join(parts)

    def mark_used(self, entry_ids: list[str]) -> None:
        if not entry_ids:
            return
        placeholders = ",".join("?" for _ in entry_ids)
        with self._connection() as connection:
            connection.execute(
                f"""
                UPDATE knowledge_entries
                SET use_count = use_count + 1, last_used_at = ?
                WHERE id IN ({placeholders})
                """,
                (_now(), *entry_ids),
            )
            connection.commit()

    def record_run(
        self,
        user_id: str,
        mode: str,
        generated_image: bool,
        source_text: str,
        instructions: str,
        output_text: str,
        image_paths: list[str],
        knowledge_ids: list[str],
        model: str,
        request_payload: dict | None = None,
        corpus_ids: list[str] | None = None,
    ) -> str:
        run_id = uuid4().hex
        created_at = _now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO generation_runs(
                    id, user_id, mode, generated_image, source_text, instructions,
                    output_text, image_paths, knowledge_ids, model, created_at,
                    request_payload, corpus_ids
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    user_id,
                    mode,
                    int(generated_image),
                    source_text,
                    instructions,
                    output_text,
                    json.dumps(image_paths, ensure_ascii=False),
                    json.dumps(list(dict.fromkeys(knowledge_ids))),
                    model,
                    created_at,
                    json.dumps(request_payload or {}, ensure_ascii=False),
                    json.dumps(list(dict.fromkeys(corpus_ids or []))),
                ),
            )
            self._write_normalized_run(
                connection,
                run_id,
                user_id,
                mode,
                generated_image,
                source_text,
                instructions,
                output_text,
                image_paths,
                knowledge_ids,
                model,
                request_payload or {},
                list(dict.fromkeys(corpus_ids or [])),
                created_at,
            )
            connection.commit()
        return run_id

    def _hydrate_normalized_row(self, connection: sqlite3.Connection, row: sqlite3.Row) -> dict:
        payload = dict(row)
        assets = connection.execute(
            "SELECT path FROM generation_assets WHERE record_id=? ORDER BY position, id",
            (row["id"],),
        ).fetchall()
        payload["image_paths"] = json.dumps([str(item[0]) for item in assets], ensure_ascii=False)
        for reference_type, field in (("knowledge", "knowledge_ids"), ("corpus", "corpus_ids")):
            refs = connection.execute(
                "SELECT reference_id FROM generation_references WHERE record_id=? AND reference_type=? ORDER BY reference_id",
                (row["id"], reference_type),
            ).fetchall()
            payload[field] = json.dumps([str(item[0]) for item in refs], ensure_ascii=False)
        if payload.get("feedback") is None:
            payload["feedback"] = ""
        if payload.get("reusable_lesson") is None:
            payload["reusable_lesson"] = ""
        return payload

    def list_runs(
        self,
        user_id: str,
        is_admin: bool,
        query: str = "",
        limit: int = 30,
        offset: int = 0,
    ) -> dict:
        clauses: list[str] = []
        values: list[object] = []
        if not is_admin:
            clauses.append("r.user_id = ?")
            values.append(user_id)
        if query.strip():
            pattern = f"%{query.strip()}%"
            clauses.append("(i.source_text LIKE ? OR o.output_text LIKE ? OR i.request_payload LIKE ?)")
            values.extend((pattern, pattern, pattern))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as connection:
            total = connection.execute(
                f"""SELECT COUNT(*) AS total FROM generation_records r
                    LEFT JOIN generation_inputs i ON i.record_id=r.id
                    LEFT JOIN generation_outputs o ON o.record_id=r.id {where}""",
                values,
            ).fetchone()
            rows = connection.execute(
                f"""SELECT r.*, i.source_text, i.instructions, i.request_payload,
                           o.output_text, f.rating, f.feedback, f.reusable_lesson, f.feedback_at
                    FROM generation_records r
                    LEFT JOIN generation_inputs i ON i.record_id=r.id
                    LEFT JOIN generation_outputs o ON o.record_id=r.id
                    LEFT JOIN generation_feedback f ON f.record_id=r.id {where}
                    ORDER BY r.created_at DESC, r.id DESC LIMIT ? OFFSET ?""",
                (*values, max(1, min(limit, 100)), max(0, offset)),
            ).fetchall()
            rows = [self._hydrate_normalized_row(connection, row) for row in rows]
        return {"items": [self._run_payload(row, summary=True) for row in rows], "total": int(total["total"] or 0)}

    def get_run(self, run_id: str, user_id: str, is_admin: bool) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                """SELECT r.*, i.source_text, i.instructions, i.request_payload,
                          o.output_text, f.rating, f.feedback, f.reusable_lesson, f.feedback_at
                   FROM generation_records r
                   LEFT JOIN generation_inputs i ON i.record_id=r.id
                   LEFT JOIN generation_outputs o ON o.record_id=r.id
                   LEFT JOIN generation_feedback f ON f.record_id=r.id
                   WHERE r.id=?""", (run_id,)
            ).fetchone()
            if row:
                row = self._hydrate_normalized_row(connection, row)
        if not row or (row["user_id"] != user_id and not is_admin):
            raise GenerationRunNotFound("生成记录不存在")
        return self._run_payload(row, summary=False)

    def delete_run(self, run_id: str, user_id: str, is_admin: bool) -> None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT user_id FROM generation_records WHERE id = ?", (run_id,)
            ).fetchone()
            if not row or (row["user_id"] != user_id and not is_admin):
                raise GenerationRunNotFound("生成记录不存在")
            connection.execute("DELETE FROM generation_records WHERE id = ?", (run_id,))
            connection.execute("DELETE FROM generation_runs WHERE id = ?", (run_id,))
            connection.commit()

    def add_feedback(
        self,
        run_id: str,
        user_id: str,
        is_admin: bool,
        rating: int,
        feedback: str,
        reusable_lesson: str,
    ) -> dict:
        feedback = feedback.strip()
        reusable_lesson = reusable_lesson.strip()
        if not 1 <= rating <= 5:
            raise KnowledgeBaseError("评分必须在 1 到 5 之间")
        if len(feedback) > 2_000 or len(reusable_lesson) > 4_000:
            raise KnowledgeBaseError("反馈内容过长")
        with self._connection() as connection:
            row = connection.execute(
                """SELECT r.*, i.source_text, i.instructions, i.request_payload, o.output_text
                   FROM generation_records r
                   LEFT JOIN generation_inputs i ON i.record_id=r.id
                   LEFT JOIN generation_outputs o ON o.record_id=r.id
                   WHERE r.id=?""", (run_id,)
            ).fetchone()
            if not row:
                raise GenerationRunNotFound("生成记录不存在")
            if row["user_id"] != user_id and not is_admin:
                raise GenerationRunNotFound("生成记录不存在")
            feedback_at = _now()
            connection.execute(
                """
                UPDATE generation_runs
                SET rating = ?, feedback = ?, reusable_lesson = ?, feedback_at = ?
                WHERE id = ?
                """,
                (rating, feedback, reusable_lesson, feedback_at, run_id),
            )
            connection.execute(
                """
                INSERT INTO generation_feedback(record_id, rating, feedback, reusable_lesson, feedback_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(record_id) DO UPDATE SET
                    rating=excluded.rating,
                    feedback=excluded.feedback,
                    reusable_lesson=excluded.reusable_lesson,
                    feedback_at=excluded.feedback_at
                """,
                (run_id, rating, feedback, reusable_lesson, feedback_at),
            )
            connection.execute(
                "UPDATE generation_runs SET rating=?, feedback=?, reusable_lesson=?, feedback_at=? WHERE id=?",
                (rating, feedback, reusable_lesson, feedback_at, run_id),
            )
            connection.commit()
        created_entry = None
        if reusable_lesson:
            kind = "image" if row["generated_image"] else "note"
            created_entry = self.create_entry(
                kind,
                f"生成反馈 {run_id[:8]}",
                reusable_lesson,
                ["生成反馈", f"{rating}星"],
                min(100, 50 + rating * 10),
                user_id,
                active=rating >= 4,
                origin="feedback",
            )
        return {
            "ok": True,
            "run_id": run_id,
            "rating": rating,
            "knowledge_entry": created_entry,
        }

    @staticmethod
    def _json_value(value: str, fallback):
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return fallback
        return parsed if isinstance(parsed, type(fallback)) else fallback

    @classmethod
    def _run_payload(cls, row: sqlite3.Row, *, summary: bool) -> dict:
        request_payload = cls._json_value(row["request_payload"], {})
        output_text = str(row["output_text"])
        source_text = str(row["source_text"])
        title = str(request_payload.get("product_name") or "").strip()
        if not title:
            candidates = output_text if output_text.strip() else source_text
            title = next(
                (line.strip().lstrip("# ") for line in candidates.splitlines() if line.strip()),
                "未命名生成记录",
            )
        payload = {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "mode": str(row["mode"]),
            "title": title[:120],
            "generated_image": bool(row["generated_image"]),
            "output_preview": output_text[:240],
            "image_paths": cls._json_value(row["image_paths"], []),
            "knowledge_ids": cls._json_value(row["knowledge_ids"], []),
            "corpus_ids": cls._json_value(row["corpus_ids"], []),
            "model": str(row["model"]),
            "created_at": int(row["created_at"]),
            "storage": "generation_records_v2",
            "rating": int(row["rating"]) if row["rating"] is not None else None,
            "feedback": str(row["feedback"]),
            "reusable_lesson": str(row["reusable_lesson"]),
        }
        if not summary:
            payload.update(
                {
                    "source_text": source_text,
                    "instructions": str(row["instructions"]),
                    "output_text": output_text,
                    "request_payload": request_payload,
                    "feedback_at": (
                        int(row["feedback_at"]) if row["feedback_at"] else None
                    ),
                }
            )
        return payload

    @classmethod
    def _corpus_payload(cls, row: sqlite3.Row, *, summary: bool) -> dict:
        content = str(row["content"])
        payload = {
            "id": str(row["id"]),
            "source_name": str(row["source_name"]),
            "record_number": int(row["record_number"]),
            "title": str(row["title"]),
            "product_name": str(row["product_name"]),
            "content_preview": content[:260],
            "tags": cls._json_value(row["tags"], []),
            "source_url": str(row["source_url"]),
            "product_url": str(row["product_url"]),
            "add_to_cart_24h": (
                int(row["add_to_cart_24h"])
                if row["add_to_cart_24h"] is not None
                else None
            ),
            "followers_text": str(row["followers_text"]),
            "sales_text": str(row["sales_text"]),
            "image_paths": cls._json_value(row["image_paths"], []),
            "use_count": int(row["use_count"]),
            "last_used_at": (
                int(row["last_used_at"]) if row["last_used_at"] else None
            ),
            "imported_at": int(row["imported_at"]),
        }
        if not summary:
            payload["content"] = content
        return payload

    @staticmethod
    def _entry_payload(row: sqlite3.Row) -> dict:
        return {
            "id": str(row["id"]),
            "kind": str(row["kind"]),
            "title": str(row["title"]),
            "content": str(row["content"]),
            "tags": json.loads(row["tags"]),
            "priority": int(row["priority"]),
            "active": bool(row["active"]),
            "origin": str(row["origin"]),
            "created_at": int(row["created_at"]),
            "updated_at": int(row["updated_at"]),
            "use_count": int(row["use_count"]),
            "last_used_at": (
                int(row["last_used_at"]) if row["last_used_at"] else None
            ),
        }
