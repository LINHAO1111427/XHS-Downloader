"""Account-scoped Xiaohongshu operation workspaces.

The global knowledge base remains the bottom layer.  This module adds the
second layer: one durable pool per operated account, containing benchmark
accounts, benchmark/traffic notes, products and generated content records.
"""
from __future__ import annotations

import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from shutil import copyfile
from threading import Event, RLock
from time import time
from typing import Annotated, Literal
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from billing import TEXT_COST, BillingError, QuotaExceeded
from knowledge_base import KnowledgeBaseError
from product_images import cache_product_images
from source.application.product import extract_products
from viral_notes import (
    NOTE_ID,
    PlatformError,
    ViralError,
    ViralRules,
    XhsDiscoveryClient,
    follower_count,
    normalize_note,
    parse_count,
    pick,
)


JSON_FIELDS = {
    "keywords",
    "image_urls",
    "image_paths",
    "video_paths",
    "tags",
    "metrics",
    "products",
    "structure",
    "request",
    "result",
    "rewrite_job_ids",
}


class OperationError(ValueError):
    pass


class SpaceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, Field(min_length=1, max_length=80)]
    account_name: Annotated[str, Field(max_length=80)] = ""
    account_url: Annotated[str, Field(max_length=2_048)] = ""
    positioning: Annotated[str, Field(max_length=2_000)] = ""
    target_audience: Annotated[str, Field(max_length=1_000)] = ""
    tone: Annotated[str, Field(max_length=1_000)] = ""
    keywords: Annotated[list[str], Field(max_length=20)] = Field(default_factory=list)

    @field_validator("keywords")
    @classmethod
    def clean_keywords(cls, values):
        cleaned = list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
        if any(len(value) > 50 for value in cleaned):
            raise ValueError("单个关键词不能超过 50 个字符")
        return cleaned


class BenchmarkAccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: Annotated[str, Field(min_length=1, max_length=2_048)]
    nickname: Annotated[str, Field(max_length=100)] = ""
    note: Annotated[str, Field(max_length=1_000)] = ""


class BenchmarkNoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: Annotated[str, Field(min_length=1, max_length=5_000)]


class ProductInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_platform: Literal["manual", "1688", "xhs"] = "manual"
    source_product_id: Annotated[str, Field(max_length=200)] = ""
    title: Annotated[str, Field(max_length=300)] = ""
    url: Annotated[str, Field(max_length=2_048)] = ""
    description: Annotated[str, Field(max_length=4_000)] = ""
    selling_points: Annotated[str, Field(max_length=4_000)] = ""
    target_audience: Annotated[str, Field(max_length=1_000)] = ""
    category: Annotated[str, Field(max_length=200)] = ""
    keywords: Annotated[list[str], Field(max_length=20)] = Field(default_factory=list)
    image_paths: Annotated[list[str], Field(max_length=30)] = Field(default_factory=list)
    image_urls: Annotated[list[str], Field(max_length=30)] = Field(default_factory=list)
    video_paths: Annotated[list[str], Field(max_length=20)] = Field(default_factory=list)


class DiscoveryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: Annotated[str, Field(max_length=64)] = ""
    keywords: Annotated[list[str], Field(max_length=5)] = Field(default_factory=list)
    hours: Annotated[int, Field(ge=1, le=168)] = 72
    limit: Annotated[int, Field(ge=1, le=50)] = 20


class OperationGenerateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: Annotated[str, Field(min_length=1, max_length=64)]
    content_type: Literal["graphic", "video"] = "graphic"
    reference_note_ids: Annotated[list[str], Field(min_length=1, max_length=6)]
    copywriting_mode: Literal["2", "3", "4", "5"] = "2"
    article_count: Annotated[int, Field(ge=1, le=10)] = 1
    image_count: Annotated[int, Field(ge=1, le=6)] = 6
    style: Literal["natural", "detail", "scene"] = "natural"
    instructions: Annotated[str, Field(max_length=2_000)] = ""


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value, fallback):
    try:
        return json.loads(value) if value else deepcopy(fallback)
    except (TypeError, ValueError):
        return deepcopy(fallback)


def note_structure(title: str, body: str) -> dict:
    """Build a deterministic style contract without pretending to understand images."""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n|\r?\n", body) if part.strip()]
    hashtags = re.findall(r"[#＃]([^#＃\s]+)", body)
    emoji = re.findall(
        "[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27BF]",
        title + body,
    )
    sentences = [part.strip() for part in re.split(r"[。！？!?\n]+", body) if part.strip()]
    return {
        "title_chars": len(title.strip()),
        "body_chars": len(re.sub(r"\s+", "", body)),
        "paragraph_count": len(paragraphs),
        "paragraph_chars": [len(re.sub(r"\s+", "", part)) for part in paragraphs],
        "opening": sentences[0][:100] if sentences else "",
        "ending": sentences[-1][-100:] if sentences else "",
        "emoji_count": len(emoji),
        "hashtag_count": len(hashtags),
        "question_count": body.count("?") + body.count("？"),
        "exclamation_count": body.count("!") + body.count("！"),
    }


def _row(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    value = dict(row)
    for key in JSON_FIELDS & value.keys():
        fallback = [] if key not in {"metrics", "structure", "request", "result"} else {}
        value[key] = _loads(value[key], fallback)
    return value


class OperationStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS operation_spaces (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    account_name TEXT NOT NULL DEFAULT '',
                    account_url TEXT NOT NULL DEFAULT '',
                    positioning TEXT NOT NULL DEFAULT '',
                    target_audience TEXT NOT NULL DEFAULT '',
                    tone TEXT NOT NULL DEFAULT '',
                    keywords TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS operation_spaces_owner
                    ON operation_spaces(owner_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS operation_benchmark_accounts (
                    id TEXT PRIMARY KEY,
                    space_id TEXT NOT NULL REFERENCES operation_spaces(id) ON DELETE CASCADE,
                    owner_id TEXT NOT NULL,
                    platform_user_id TEXT NOT NULL DEFAULT '',
                    nickname TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    followers INTEGER,
                    note_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT '待采集',
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS operation_accounts_space
                    ON operation_benchmark_accounts(space_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS operation_notes (
                    id TEXT PRIMARY KEY,
                    space_id TEXT NOT NULL REFERENCES operation_spaces(id) ON DELETE CASCADE,
                    owner_id TEXT NOT NULL,
                    benchmark_account_id TEXT REFERENCES operation_benchmark_accounts(id) ON DELETE SET NULL,
                    source_kind TEXT NOT NULL,
                    source_key TEXT NOT NULL,
                    note_id TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    note_type TEXT NOT NULL DEFAULT '',
                    author TEXT NOT NULL DEFAULT '',
                    author_id TEXT NOT NULL DEFAULT '',
                    cover TEXT NOT NULL DEFAULT '',
                    image_urls TEXT NOT NULL DEFAULT '[]',
                    image_paths TEXT NOT NULL DEFAULT '[]',
                    tags TEXT NOT NULL DEFAULT '[]',
                    metrics TEXT NOT NULL DEFAULT '{}',
                    products TEXT NOT NULL DEFAULT '[]',
                    structure TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(space_id, source_key)
                );
                CREATE INDEX IF NOT EXISTS operation_notes_space
                    ON operation_notes(space_id, source_kind, updated_at DESC);

                CREATE TABLE IF NOT EXISTS operation_products (
                    id TEXT PRIMARY KEY,
                    space_id TEXT NOT NULL REFERENCES operation_spaces(id) ON DELETE CASCADE,
                    owner_id TEXT NOT NULL,
                    source_platform TEXT NOT NULL DEFAULT 'manual',
                    external_id TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL,
                    url TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    selling_points TEXT NOT NULL DEFAULT '',
                    target_audience TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    keywords TEXT NOT NULL DEFAULT '[]',
                    image_urls TEXT NOT NULL DEFAULT '[]',
                    image_paths TEXT NOT NULL DEFAULT '[]',
                    video_paths TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS operation_products_space
                    ON operation_products(space_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS operation_generations (
                    id TEXT PRIMARY KEY,
                    space_id TEXT NOT NULL REFERENCES operation_spaces(id) ON DELETE CASCADE,
                    owner_id TEXT NOT NULL,
                    product_id TEXT NOT NULL DEFAULT '',
                    content_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    request TEXT NOT NULL DEFAULT '{}',
                    result TEXT NOT NULL DEFAULT '{}',
                    rewrite_job_ids TEXT NOT NULL DEFAULT '[]',
                    error TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS operation_generations_space
                    ON operation_generations(space_id, created_at DESC);
                """
            )
            note_columns = {
                str(row[1]) for row in db.execute("PRAGMA table_info(operation_notes)").fetchall()
            }
            if "image_paths" not in note_columns:
                db.execute(
                    "ALTER TABLE operation_notes ADD COLUMN image_paths TEXT NOT NULL DEFAULT '[]'"
                )

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def create_space(self, owner_id: str, payload: dict) -> dict:
        now = time()
        space_id = uuid4().hex
        with self.connection() as db:
            db.execute(
                """INSERT INTO operation_spaces
                (id, owner_id, name, account_name, account_url, positioning,
                 target_audience, tone, keywords, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    space_id,
                    owner_id,
                    payload["name"].strip(),
                    payload.get("account_name", "").strip(),
                    payload.get("account_url", "").strip(),
                    payload.get("positioning", "").strip(),
                    payload.get("target_audience", "").strip(),
                    payload.get("tone", "").strip(),
                    _json(payload.get("keywords", [])),
                    now,
                    now,
                ),
            )
        return self.get_space(owner_id, space_id)

    def update_space(self, owner_id: str, space_id: str, payload: dict) -> dict:
        self.get_space(owner_id, space_id)
        with self.connection() as db:
            db.execute(
                """UPDATE operation_spaces SET name=?, account_name=?, account_url=?,
                positioning=?, target_audience=?, tone=?, keywords=?, updated_at=?
                WHERE id=? AND owner_id=?""",
                (
                    payload["name"].strip(),
                    payload.get("account_name", "").strip(),
                    payload.get("account_url", "").strip(),
                    payload.get("positioning", "").strip(),
                    payload.get("target_audience", "").strip(),
                    payload.get("tone", "").strip(),
                    _json(payload.get("keywords", [])),
                    time(),
                    space_id,
                    owner_id,
                ),
            )
        return self.get_space(owner_id, space_id)

    def get_space(self, owner_id: str, space_id: str) -> dict:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM operation_spaces WHERE id=? AND owner_id=?",
                (space_id, owner_id),
            ).fetchone()
        if row is None:
            raise KeyError(space_id)
        return _row(row)

    def spaces(self, owner_id: str) -> list[dict]:
        with self.connection() as db:
            rows = db.execute(
                """SELECT s.*,
                (SELECT COUNT(*) FROM operation_benchmark_accounts a WHERE a.space_id=s.id) benchmark_account_count,
                (SELECT COUNT(*) FROM operation_notes n WHERE n.space_id=s.id) note_count,
                (SELECT COUNT(*) FROM operation_products p WHERE p.space_id=s.id) product_count,
                (SELECT COUNT(*) FROM operation_generations g WHERE g.space_id=s.id) generation_count
                FROM operation_spaces s WHERE owner_id=? ORDER BY updated_at DESC""",
                (owner_id,),
            ).fetchall()
        return [_row(row) for row in rows]

    def delete_space(self, owner_id: str, space_id: str) -> None:
        self.get_space(owner_id, space_id)
        with self.connection() as db:
            db.execute(
                "DELETE FROM operation_spaces WHERE id=? AND owner_id=?",
                (space_id, owner_id),
            )

    def add_account(self, owner_id: str, space_id: str, payload: dict) -> dict:
        self.get_space(owner_id, space_id)
        account_id = uuid4().hex
        now = time()
        platform_id = xhs_user_id(payload["url"])
        with self.connection() as db:
            db.execute(
                """INSERT INTO operation_benchmark_accounts
                (id, space_id, owner_id, platform_user_id, nickname, url, note,
                 followers, note_count, status, last_error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, '待采集', '', ?, ?)""",
                (
                    account_id,
                    space_id,
                    owner_id,
                    platform_id,
                    payload.get("nickname", "").strip(),
                    payload["url"].strip(),
                    payload.get("note", "").strip(),
                    now,
                    now,
                ),
            )
        return self.get_account(owner_id, space_id, account_id)

    def get_account(self, owner_id: str, space_id: str, account_id: str) -> dict:
        self.get_space(owner_id, space_id)
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM operation_benchmark_accounts WHERE id=? AND space_id=? AND owner_id=?",
                (account_id, space_id, owner_id),
            ).fetchone()
        if row is None:
            raise KeyError(account_id)
        return _row(row)

    def update_account(self, owner_id: str, space_id: str, account_id: str, **changes) -> dict:
        account = self.get_account(owner_id, space_id, account_id)
        allowed = {"platform_user_id", "nickname", "followers", "note_count", "status", "last_error"}
        values = {key: value for key, value in changes.items() if key in allowed}
        if values:
            values["updated_at"] = time()
            assignment = ", ".join(f"{key}=?" for key in values)
            with self.connection() as db:
                db.execute(
                    f"UPDATE operation_benchmark_accounts SET {assignment} WHERE id=? AND space_id=? AND owner_id=?",
                    (*values.values(), account_id, space_id, owner_id),
                )
        return self.get_account(owner_id, space_id, account_id)

    def delete_account(self, owner_id: str, space_id: str, account_id: str) -> None:
        self.get_account(owner_id, space_id, account_id)
        with self.connection() as db:
            db.execute(
                "DELETE FROM operation_benchmark_accounts WHERE id=? AND space_id=? AND owner_id=?",
                (account_id, space_id, owner_id),
            )

    def upsert_note(self, owner_id: str, space_id: str, payload: dict) -> dict:
        self.get_space(owner_id, space_id)
        note_id = str(payload.get("note_id") or "").strip()
        url = str(payload.get("url") or "").strip()
        source_key = note_id or sha256(
            (url + "\n" + str(payload.get("title") or "") + "\n" + str(payload.get("body") or "")).encode("utf8")
        ).hexdigest()[:32]
        local_id = uuid4().hex
        now = time()
        body = str(payload.get("body") or payload.get("description") or "").strip()
        title = str(payload.get("title") or "").strip()
        structure = payload.get("structure") or note_structure(title, body)
        metrics = payload.get("metrics") or {
            key: payload.get(key)
            for key in ("likes", "collects", "comments", "shares", "followers", "interactions", "score", "published_at")
            if payload.get(key) is not None
        }
        values = (
            local_id,
            space_id,
            owner_id,
            payload.get("benchmark_account_id"),
            str(payload.get("source_kind") or "benchmark_note"),
            source_key,
            note_id,
            url,
            title,
            body,
            str(payload.get("type") or payload.get("note_type") or ""),
            str(payload.get("author") or ""),
            str(payload.get("author_id") or ""),
            str(payload.get("cover") or ""),
            _json(list(dict.fromkeys(payload.get("image_urls") or []))[:20]),
            _json(list(dict.fromkeys(payload.get("image_paths") or []))[:20]),
            _json(list(dict.fromkeys(payload.get("tags") or []))[:30]),
            _json(metrics),
            _json((payload.get("products") or [])[:30]),
            _json(structure),
            now,
            now,
        )
        with self.connection() as db:
            db.execute(
                """INSERT INTO operation_notes
                (id, space_id, owner_id, benchmark_account_id, source_kind, source_key,
                 note_id, url, title, body, note_type, author, author_id, cover,
                 image_urls, image_paths, tags, metrics, products, structure, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(space_id, source_key) DO UPDATE SET
                 benchmark_account_id=COALESCE(excluded.benchmark_account_id, operation_notes.benchmark_account_id),
                 source_kind=CASE
                   WHEN operation_notes.source_kind IN ('benchmark_note','benchmark_account','benchmark_account_viral')
                        AND excluded.source_kind='traffic_note'
                   THEN operation_notes.source_kind ELSE excluded.source_kind END,
                 note_id=excluded.note_id, url=excluded.url,
                 title=excluded.title, body=excluded.body, note_type=excluded.note_type,
                 author=excluded.author, author_id=excluded.author_id, cover=excluded.cover,
                 image_urls=excluded.image_urls,
                 image_paths=CASE WHEN excluded.image_paths='[]' THEN operation_notes.image_paths ELSE excluded.image_paths END,
                 tags=excluded.tags, metrics=excluded.metrics,
                 products=excluded.products, structure=excluded.structure, updated_at=excluded.updated_at""",
                values,
            )
            row = db.execute(
                "SELECT * FROM operation_notes WHERE space_id=? AND source_key=?",
                (space_id, source_key),
            ).fetchone()
        return _row(row)

    def notes(self, owner_id: str, space_id: str, ids: list[str] | None = None) -> list[dict]:
        self.get_space(owner_id, space_id)
        with self.connection() as db:
            if ids:
                placeholders = ",".join("?" for _ in ids)
                rows = db.execute(
                    f"SELECT * FROM operation_notes WHERE owner_id=? AND space_id=? AND id IN ({placeholders}) ORDER BY updated_at DESC",
                    (owner_id, space_id, *ids),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM operation_notes WHERE owner_id=? AND space_id=? ORDER BY updated_at DESC",
                    (owner_id, space_id),
                ).fetchall()
        found = [_row(row) for row in rows]
        if ids and {item["id"] for item in found} != set(ids):
            raise KeyError("note")
        return found

    def delete_note(self, owner_id: str, space_id: str, note_id: str) -> None:
        if not self.notes(owner_id, space_id, [note_id]):
            raise KeyError(note_id)
        with self.connection() as db:
            db.execute(
                "DELETE FROM operation_notes WHERE id=? AND space_id=? AND owner_id=?",
                (note_id, space_id, owner_id),
            )

    def add_product(self, owner_id: str, space_id: str, payload: dict, product_id: str | None = None) -> dict:
        self.get_space(owner_id, space_id)
        if not str(payload.get("title") or "").strip():
            raise OperationError("请填写商品名称，或先从商品素材库采集商品")
        external_id = str(payload.get("source_product_id", payload.get("external_id", "")) or "").strip()
        source_platform = str(payload.get("source_platform", "manual"))
        if product_id is None and external_id:
            with self.connection() as db:
                existing = db.execute(
                    """SELECT * FROM operation_products
                    WHERE owner_id=? AND space_id=? AND source_platform=? AND external_id=?
                    ORDER BY updated_at DESC LIMIT 1""",
                    (owner_id, space_id, source_platform, external_id),
                ).fetchone()
            if existing:
                current = _row(existing)
                with self.connection() as db:
                    db.execute(
                        """UPDATE operation_products SET title=?, url=?, description=?, selling_points=?,
                        target_audience=?, category=?, keywords=?, image_urls=?, image_paths=?, video_paths=?, updated_at=?
                        WHERE id=? AND owner_id=?""",
                        (
                            str(payload.get("title") or current["title"]).strip(),
                            str(payload.get("url") or current["url"]).strip(),
                            str(payload.get("description") or current["description"]).strip(),
                            str(payload.get("selling_points") or current["selling_points"]).strip(),
                            str(payload.get("target_audience") or current["target_audience"]).strip(),
                            str(payload.get("category") or current["category"]).strip(),
                            _json(payload.get("keywords") or current["keywords"]),
                            _json(payload.get("image_urls") or current["image_urls"]),
                            _json(payload.get("image_paths") or current["image_paths"]),
                            _json(payload.get("video_paths") or current["video_paths"]),
                            time(),
                            current["id"],
                            owner_id,
                        ),
                    )
                return self.get_product(owner_id, space_id, current["id"])
        product_id = product_id or uuid4().hex
        now = time()
        with self.connection() as db:
            db.execute(
                """INSERT INTO operation_products
                (id, space_id, owner_id, source_platform, external_id, title, url,
                 description, selling_points, target_audience, category, keywords,
                 image_urls, image_paths, video_paths, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    product_id,
                    space_id,
                    owner_id,
                    source_platform,
                    external_id,
                    str(payload["title"]).strip(),
                    str(payload.get("url") or "").strip(),
                    str(payload.get("description") or "").strip(),
                    str(payload.get("selling_points") or "").strip(),
                    str(payload.get("target_audience") or "").strip(),
                    str(payload.get("category") or "").strip(),
                    _json(payload.get("keywords") or []),
                    _json(payload.get("image_urls") or []),
                    _json(payload.get("image_paths") or []),
                    _json(payload.get("video_paths") or []),
                    now,
                    now,
                ),
            )
        return self.get_product(owner_id, space_id, product_id)

    def get_product(self, owner_id: str, space_id: str, product_id: str) -> dict:
        self.get_space(owner_id, space_id)
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM operation_products WHERE id=? AND space_id=? AND owner_id=?",
                (product_id, space_id, owner_id),
            ).fetchone()
        if row is None:
            raise KeyError(product_id)
        return _row(row)

    def products(self, owner_id: str, space_id: str) -> list[dict]:
        self.get_space(owner_id, space_id)
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM operation_products WHERE space_id=? AND owner_id=? ORDER BY updated_at DESC",
                (space_id, owner_id),
            ).fetchall()
        return [_row(row) for row in rows]

    def delete_product(self, owner_id: str, space_id: str, product_id: str) -> None:
        self.get_product(owner_id, space_id, product_id)
        with self.connection() as db:
            db.execute(
                "DELETE FROM operation_products WHERE id=? AND space_id=? AND owner_id=?",
                (product_id, space_id, owner_id),
            )

    def create_generation(self, owner_id: str, space_id: str, request: dict) -> dict:
        self.get_space(owner_id, space_id)
        generation_id = uuid4().hex
        now = time()
        with self.connection() as db:
            db.execute(
                """INSERT INTO operation_generations
                (id, space_id, owner_id, product_id, content_type, status, title,
                 request, result, rewrite_job_ids, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'pending', '', ?, '{}', '[]', '', ?, ?)""",
                (
                    generation_id,
                    space_id,
                    owner_id,
                    request.get("product_id", ""),
                    request.get("content_type", "graphic"),
                    _json(request),
                    now,
                    now,
                ),
            )
        return self.get_generation(owner_id, space_id, generation_id)

    def update_generation(self, owner_id: str, space_id: str, generation_id: str, **changes) -> dict:
        self.get_generation(owner_id, space_id, generation_id)
        allowed = {"status", "title", "result", "rewrite_job_ids", "error"}
        values = {key: (_json(value) if key in {"result", "rewrite_job_ids"} else value)
                  for key, value in changes.items() if key in allowed}
        values["updated_at"] = time()
        assignment = ", ".join(f"{key}=?" for key in values)
        with self.connection() as db:
            db.execute(
                f"UPDATE operation_generations SET {assignment} WHERE id=? AND space_id=? AND owner_id=?",
                (*values.values(), generation_id, space_id, owner_id),
            )
        return self.get_generation(owner_id, space_id, generation_id)

    def get_generation(self, owner_id: str, space_id: str, generation_id: str) -> dict:
        self.get_space(owner_id, space_id)
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM operation_generations WHERE id=? AND space_id=? AND owner_id=?",
                (generation_id, space_id, owner_id),
            ).fetchone()
        if row is None:
            raise KeyError(generation_id)
        return _row(row)

    def generations(self, owner_id: str, space_id: str) -> list[dict]:
        self.get_space(owner_id, space_id)
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM operation_generations WHERE space_id=? AND owner_id=? ORDER BY created_at DESC LIMIT 100",
                (space_id, owner_id),
            ).fetchall()
        return [_row(row) for row in rows]

    def detail(self, owner_id: str, space_id: str) -> dict:
        space = self.get_space(owner_id, space_id)
        with self.connection() as db:
            accounts = [_row(row) for row in db.execute(
                "SELECT * FROM operation_benchmark_accounts WHERE space_id=? AND owner_id=? ORDER BY updated_at DESC",
                (space_id, owner_id),
            ).fetchall()]
        return {
            "space": space,
            "benchmark_accounts": accounts,
            "notes": self.notes(owner_id, space_id),
            "products": self.products(owner_id, space_id),
            "generations": self.generations(owner_id, space_id),
        }

    def prompt_context(self, owner_id: str, space_id: str, note_ids: list[str], product_id: str) -> str:
        space = self.get_space(owner_id, space_id)
        product = self.get_product(owner_id, space_id, product_id)
        notes = self.notes(owner_id, space_id, note_ids) if note_ids else []
        lines = [
            "账号级运营知识（优先级低于真实商品资料，高于通用案例）：",
            f"运营账号：{space['account_name'] or space['name']}",
            f"账号定位：{space['positioning'] or '未填写'}",
            f"目标人群：{space['target_audience'] or product['target_audience'] or '未填写'}",
            f"语言与画面调性：{space['tone'] or '未填写'}",
            f"账号关键词：{'、'.join(space['keywords']) or '未填写'}",
            f"当前商品：{product['title']}",
            f"商品资料：{product['description'] or '未填写'}",
            f"真实卖点：{product['selling_points'] or '未填写'}",
            "\n对标约束：逐篇读取标题、正文、结构指纹和数据；迁移第一屏功能、段落职责、信息密度、情绪曲线与构图逻辑，"
            "不复制连续原句，不迁移对方的品牌、产品事实、个人经历或无法验证的功效。",
        ]
        for index, note in enumerate(notes, 1):
            lines.append(
                f"[对标 {index}] local_id={note['id']} note_id={note['note_id']} 来源={note['source_kind']}\n"
                f"标题：{note['title']}\n正文：{note['body']}\n话题：{' '.join(note['tags'])}\n"
                f"结构指纹：{_json(note['structure'])}\n数据快照：{_json(note['metrics'])}"
            )
        return "\n\n".join(lines)


def xhs_user_id(value: str) -> str:
    text = str(value or "").strip()
    match = re.search(r"/user/profile/([a-zA-Z0-9_-]{8,80})", text)
    if match:
        return match.group(1)
    try:
        query = parse_qs(urlsplit(text).query)
        for key in ("user_id", "userId", "target_user_id"):
            if query.get(key):
                return query[key][0]
    except ValueError:
        pass
    return text if re.fullmatch(r"[a-zA-Z0-9_-]{8,80}", text) else ""


def _image_urls(card: dict) -> list[str]:
    values = []
    for item in pick(card, "image_list", "imageList") or []:
        if not isinstance(item, dict):
            continue
        value = pick(item, "url_default", "urlDefault", "url_pre", "urlPre", "url")
        value = str(value or "").strip()
        if value.startswith("//"):
            value = "https:" + value
        if value.startswith("http") and value not in values:
            values.append(value)
    return values


def _profile_name(profile: dict) -> str:
    basic = pick(profile, "basic_info", "basicInfo") or {}
    return str(pick(basic, "nickname", "nickName") or profile.get("nickname") or "")


def _posted_items(data: dict) -> list[dict]:
    raw = pick(data, "notes", "items", "note_list", "noteList") or []
    result = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        card = pick(item, "note_card", "noteCard") or item
        if isinstance(card, dict):
            if not pick(card, "note_id", "noteId") and item.get("id"):
                card = dict(card) | {"note_id": item["id"]}
            token = str(pick(item, "xsec_token", "xsecToken") or pick(card, "xsec_token", "xsecToken") or "")
            result.append({"card": card, "token": token})
    return result


def _low_follower_viral_metrics(note: dict, followers: int | None) -> dict | None:
    """Return a verified low-follower viral snapshot, or None when it does not qualify."""
    if followers is None or followers > 100_000:
        return None
    counts = {key: parse_count(note.get(key)) for key in ("likes", "collects", "comments", "shares")}
    if any(value is None for value in counts.values()):
        return None
    interactions = sum(int(value) for value in counts.values())
    ratio = interactions / max(followers, 100)
    if interactions < 300 or ratio < 0.05:
        return None
    return {
        **counts,
        "followers": followers,
        "interactions": interactions,
        "ratio": round(ratio, 4),
        "score": round(interactions * min(ratio, 10), 2),
        "is_low_follower_viral": True,
    }


class OperationService:
    def __init__(
        self,
        store: OperationStore,
        runtime,
        gateway,
        knowledge,
        billing,
        load_images,
        viral_service,
        collectors: dict,
        remix_manager=None,
        slideshow_manager=None,
    ):
        self.store = store
        self.runtime = runtime
        self.gateway = gateway
        self.knowledge = knowledge
        self.billing = billing
        self.load_images = load_images
        self.viral_service = viral_service
        self.collectors = collectors
        self.remix_manager = remix_manager
        self.slideshow_manager = slideshow_manager
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="xhs-operation")
        self.lock = RLock()
        self.stop = Event()
        self.jobs: dict[str, dict] = {}
        self.closed = False

    def _cache_remote_images(self, space_id: str, asset_kind: str, asset_id: str, urls: list[str]) -> list[str]:
        if not urls:
            return []
        root = self.runtime.download_root().resolve()
        relative_root = Path("小红书运营") / space_id / asset_kind
        cached, _errors = cache_product_images(root / relative_root, asset_id, urls[:12])
        return [(relative_root / path).as_posix() for path in cached]

    def _copy_reference_images(self, space_id: str, note_id: str, paths: list[str]) -> list[str]:
        root = self.runtime.download_root().resolve()
        folder = root / "小红书运营" / space_id / "对标笔记" / sha256(note_id.encode("utf8")).hexdigest()[:24]
        folder.mkdir(parents=True, exist_ok=True)
        copied = []
        for index, value in enumerate(paths[:20]):
            try:
                source = (root / value).resolve()
                if not source.is_relative_to(root) or not source.is_file():
                    continue
                target = folder / f"image-{index + 1:02d}{source.suffix.lower()}"
                copyfile(source, target)
                copied.append(target.relative_to(root).as_posix())
            except (OSError, ValueError):
                continue
        return copied

    def _import_attached_products(
        self,
        owner_id: str,
        space_id: str,
        note: dict,
        products: list[dict],
    ) -> list[dict]:
        imported = []
        for index, product in enumerate(products[:30]):
            if not isinstance(product, dict) or not product.get("title"):
                continue
            external_id = str(product.get("product_id") or "").strip()
            identity = external_id or sha256(
                (str(product.get("url") or "") + str(product.get("title") or "")).encode("utf8")
            ).hexdigest()[:24]
            image_urls = list(dict.fromkeys(product.get("images") or []))[:12]
            image_paths = self._cache_remote_images(
                space_id, "商品", identity or f"note-product-{index}", image_urls
            )
            facts = []
            if product.get("price"):
                facts.append(f"采集时展示价格：{product['price']}")
            if product.get("shop"):
                facts.append(f"店铺：{product['shop']}")
            specs = product.get("specs") or {}
            facts.extend(f"{key}：{value}" for key, value in specs.items() if key and value)
            try:
                imported.append(self.store.add_product(owner_id, space_id, {
                    "source_platform": "xhs",
                    "source_product_id": identity,
                    "title": str(product["title"]),
                    "url": str(product.get("url") or ""),
                    "description": "；".join(facts),
                    "selling_points": "",
                    "image_urls": image_urls,
                    "image_paths": image_paths,
                    "keywords": [],
                    "target_audience": "",
                    "category": "",
                    "video_paths": [],
                }))
            except (OperationError, sqlite3.IntegrityError):
                continue
        return imported

    def shutdown(self):
        with self.lock:
            self.closed = True
            self.stop.set()
        self.executor.shutdown(wait=True, cancel_futures=True)

    def job(self, owner_id: str, job_id: str) -> dict:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job["owner_id"] != owner_id:
                raise KeyError(job_id)
            return deepcopy({key: value for key, value in job.items() if key != "owner_id"})

    def _job_update(self, job_id: str, **changes):
        with self.lock:
            self.jobs[job_id].update(changes, updated_at=time())

    def submit_account_sync(self, owner_id: str, space_id: str, account_id: str, limit: int = 20) -> dict:
        account = self.store.get_account(owner_id, space_id, account_id)
        if not account["platform_user_id"]:
            raise OperationError("没有从链接识别到账号 ID，请粘贴完整的小红书主页链接")
        with self.lock:
            if self.closed:
                raise OperationError("运营采集服务正在关闭")
            if any(job["state"] in {"pending", "processing"} and job["owner_id"] == owner_id for job in self.jobs.values()):
                raise OperationError("已有账号采集任务正在运行，请完成后再试")
            job_id = uuid4().hex
            self.jobs[job_id] = {
                "id": job_id,
                "owner_id": owner_id,
                "space_id": space_id,
                "account_id": account_id,
                "state": "pending",
                "phase": "等待采集",
                "completed": 0,
                "total": limit,
                "error": "",
                "created_at": time(),
                "updated_at": time(),
            }
        self.store.update_account(owner_id, space_id, account_id, status="排队采集", last_error="")
        self.executor.submit(self._sync_account, job_id, limit)
        return self.job(owner_id, job_id)

    def _sync_account(self, job_id: str, limit: int):
        with self.lock:
            job = deepcopy(self.jobs[job_id])
        owner_id, space_id, account_id = job["owner_id"], job["space_id"], job["account_id"]
        account = self.store.get_account(owner_id, space_id, account_id)
        client = None
        try:
            self._job_update(job_id, state="processing", phase="读取账号资料")
            self.store.update_account(owner_id, space_id, account_id, status="采集中")
            client = XhsDiscoveryClient(self.runtime.discovery_settings(), self.stop)
            profile = client.author(account["platform_user_id"])
            nickname = _profile_name(profile) or account["nickname"]
            followers = follower_count(profile)
            cursor = ""
            summaries: list[dict] = []
            for _ in range(3):
                data = client.request(
                    "GET",
                    "/api/sns/web/v1/user_posted",
                    {"num": min(30, limit), "cursor": cursor, "user_id": account["platform_user_id"], "image_formats": ["jpg", "webp", "avif"]},
                )
                page = _posted_items(data)
                summaries.extend(page)
                if len(summaries) >= limit or not data.get("has_more", data.get("hasMore", False)):
                    break
                cursor = str(pick(data, "cursor", "next_cursor", "nextCursor") or "")
                if not cursor:
                    break
            summaries = summaries[:limit]
            self._job_update(job_id, total=len(summaries), phase="筛选低粉爆款笔记")
            qualified = []
            for index, summary in enumerate(summaries):
                card, token = summary["card"], summary["token"]
                platform_note_id = str(pick(card, "note_id", "noteId") or "")
                if NOTE_ID.fullmatch(platform_note_id) and token:
                    try:
                        detail = client.request(
                            "POST",
                            "/api/sns/web/v1/feed",
                            {
                                "source_note_id": platform_note_id,
                                "image_formats": ["jpg", "webp", "avif"],
                                "extra": {"need_body_topic": "1"},
                                "xsec_source": "pc_user",
                                "xsec_token": token,
                            },
                        )
                        card = next(
                            (pick(item, "note_card", "noteCard") or {} for item in detail.get("items", [])
                             if str(pick(pick(item, "note_card", "noteCard") or {}, "note_id", "noteId") or "") == platform_note_id),
                            card,
                        )
                    except PlatformError:
                        pass
                normalized = normalize_note(card, token)
                products = extract_products(card)
                metrics = _low_follower_viral_metrics(normalized, followers)
                if metrics:
                    qualified.append((metrics["score"], normalized | {
                        "benchmark_account_id": account_id,
                        "source_kind": "benchmark_account_viral",
                        "body": normalized["description"],
                        "image_urls": _image_urls(card),
                        "products": products,
                        "metrics": metrics,
                    }))
                self._job_update(
                    job_id,
                    completed=index + 1,
                    phase=f"已分析 {index + 1}/{len(summaries)} 篇，命中 {len(qualified)} 篇低粉爆款",
                )
            qualified.sort(key=lambda item: item[0], reverse=True)
            saved_count = 0
            for _score, candidate in qualified[:limit]:
                candidate["image_paths"] = self._cache_remote_images(
                    space_id,
                    "对标笔记",
                    candidate.get("note_id") or uuid4().hex,
                    candidate.get("image_urls") or [],
                )
                saved = self.store.upsert_note(owner_id, space_id, candidate)
                self._import_attached_products(
                    owner_id, space_id, saved, candidate.get("products") or []
                )
                saved_count += 1
                self._job_update(job_id, phase=f"正在保存低粉爆款 {saved_count}/{len(qualified[:limit])}")
            self.store.update_account(
                owner_id,
                space_id,
                account_id,
                nickname=nickname,
                followers=followers,
                note_count=saved_count,
                status="已完成低粉爆款筛选",
                last_error="",
            )
            self._job_update(
                job_id,
                state="success",
                completed=len(summaries),
                phase=f"已筛选 {len(summaries)} 篇，保存 {saved_count} 篇低粉爆款",
            )
        except Exception as error:
            message = str(error)
            self.store.update_account(owner_id, space_id, account_id, status="采集失败", last_error=message)
            self._job_update(job_id, state="failed", phase="采集失败", error=message)
        finally:
            if client:
                client.close()

    def import_manual_note(self, owner_id: str, space_id: str, content: str) -> dict:
        source = self.runtime.collect_reference(content)
        if not source.get("title") and not source.get("body"):
            raise OperationError("没有采集到对标笔记正文，请检查链接和 Cookie")
        source["source_kind"] = "benchmark_note"
        source["image_paths"] = self._copy_reference_images(
            space_id,
            str(source.get("note_id") or uuid4().hex),
            source.get("image_paths") or [],
        )
        counts = {
            key: parse_count(source.get(key))
            for key in ("likes", "collects", "comments", "shares")
        }
        available = [value for value in counts.values() if value is not None]
        source["metrics"] = {
            **{key: value for key, value in counts.items() if value is not None},
            **({"interactions": sum(available)} if available else {}),
            **({"published_at": source["published_at"]} if source.get("published_at") else {}),
        }
        saved = self.store.upsert_note(owner_id, space_id, source)
        imported = self._import_attached_products(
            owner_id, space_id, saved, source.get("products") or []
        )
        saved["imported_product_count"] = len(imported)
        return saved

    def analyze_profile(self, owner_id: str, space_id: str) -> dict:
        space = self.store.get_space(owner_id, space_id)
        notes = self.store.notes(owner_id, space_id)
        products = self.store.products(owner_id, space_id)
        accounts = self.store.detail(owner_id, space_id)["benchmark_accounts"]
        if not notes and not products and not accounts:
            raise OperationError("请先添加并同步对标账号，或加入至少一篇对标笔记")
        evidence = {
            "benchmark_accounts": [
                {
                    "nickname": item["nickname"],
                    "followers": item["followers"],
                    "saved_low_follower_viral_notes": item["note_count"],
                }
                for item in accounts[:20]
            ],
            "notes": [
                {
                    "title": item["title"],
                    "body": item["body"][:1200],
                    "tags": item["tags"],
                    "metrics": item["metrics"],
                    "products": [
                        {key: product.get(key) for key in ("title", "price", "shop") if product.get(key)}
                        for product in item["products"][:5]
                        if isinstance(product, dict)
                    ],
                }
                for item in notes[:30]
            ],
            "products": [
                {
                    "title": item["title"],
                    "description": item["description"],
                    "selling_points": item["selling_points"],
                    "category": item["category"],
                }
                for item in products[:30]
            ],
        }
        workflow_context = """你是小红书电商账号定位分析师。只能根据给定的对标账号、笔记正文、互动数据和商品资料归纳，不能虚构商品事实、消费者画像或效果承诺。
需要识别：主要卖货方向、核心目标人群、内容定位、语言与画面调性、账号检索关键词。目标人群要写清人群特征、使用/浏览场景、主要痛点和决策因素；证据不足处明确写“待验证”。
只返回 JSON 对象，不要代码围栏：
{"positioning":"主要卖货方向与差异化定位","target_audience":"目标人群与场景","tone":"语言与画面调性","keywords":["关键词"],"evidence":["从素材中观察到的依据"],"uncertainties":["仍需用户确认的信息"]}。keywords 3-10 个，evidence 2-8 条。"""
        charge_id = f"operation-profile:{space_id}:{uuid4().hex}"
        try:
            receipt = self.billing.consume(
                owner_id, "text", TEXT_COST, charge_id, {"space_id": space_id}
            )
            generated = self.gateway.generate(
                _json(evidence),
                "保留已有账号名称；根据证据补全定位，不要写空泛人群。",
                "rewrite",
                [],
                workflow_context=workflow_context,
            )
            analysis = parse_json_object(generated["text"])
            for key in ("positioning", "target_audience", "tone"):
                if not isinstance(analysis.get(key), str) or not analysis[key].strip():
                    raise OperationError("账号分析结果不完整，本次点数已退回")
            keywords = analysis.get("keywords")
            if not isinstance(keywords, list):
                raise OperationError("账号分析缺少关键词，本次点数已退回")
            updated = self.store.update_space(owner_id, space_id, {
                "name": space["name"],
                "account_name": space["account_name"],
                "account_url": "",
                "positioning": analysis["positioning"].strip(),
                "target_audience": analysis["target_audience"].strip(),
                "tone": analysis["tone"].strip(),
                "keywords": list(dict.fromkeys(str(value).strip() for value in keywords if str(value).strip()))[:10],
            })
            analysis["model"] = generated["model"]
            analysis["billing"] = {
                key: value for key, value in receipt.items() if key != "usage"
            }
            return {"space": updated, "analysis": analysis}
        except Exception:
            self.billing.refund(owner_id, charge_id)
            raise

    def import_product(self, owner_id: str, space_id: str, payload: dict) -> dict:
        platform = payload.get("source_platform", "manual")
        if platform == "manual":
            return self.store.add_product(owner_id, space_id, payload)
        collector = self.collectors[platform]
        external_id = payload.get("source_product_id", "")
        source = next((item for item in collector.items() if str(item.get("product_id")) == external_id), None)
        if source is None:
            raise OperationError("商品素材库中没有这个商品，请先完成商品采集")
        existing = next(
            (
                item
                for item in self.store.products(owner_id, space_id)
                if item["source_platform"] == platform and item["external_id"] == external_id
            ),
            None,
        )
        if existing:
            return self.store.add_product(
                owner_id,
                space_id,
                {
                    **payload,
                    "title": payload.get("title") or source.get("title") or existing["title"],
                    "url": payload.get("url") or source.get("url") or existing["url"],
                },
            )
        product_id = uuid4().hex
        root = self.runtime.download_root().resolve()
        folder = root / "小红书运营" / space_id / "商品" / product_id
        folder.mkdir(parents=True, exist_ok=True)
        image_paths = []
        for index in range(min(12, len(source.get("images", [])) + len(source.get("detail_images", [])))):
            try:
                original = collector.local_image(external_id, index)
                target = folder / f"image-{index + 1:02d}{original.suffix.lower()}"
                copyfile(original, target)
                image_paths.append(target.relative_to(root).as_posix())
            except (OSError, ValueError):
                continue
        video_paths = []
        for index in range(min(6, len(source.get("videos", [])))):
            try:
                original = collector.local_video(external_id, index)
                target = folder / f"video-{index + 1:02d}{original.suffix.lower()}"
                copyfile(original, target)
                video_paths.append(target.relative_to(root).as_posix())
            except (OSError, ValueError):
                continue
        specs = source.get("specs") or {}
        description = payload.get("description") or source.get("description") or source.get("subtitle") or ""
        selling = payload.get("selling_points") or "；".join(f"{key}：{value}" for key, value in specs.items())
        return self.store.add_product(owner_id, space_id, {
            **payload,
            "title": payload.get("title") or source.get("title") or "未命名商品",
            "url": payload.get("url") or source.get("url") or "",
            "description": description,
            "selling_points": selling,
            "image_urls": source.get("image_urls") or [],
            "image_paths": image_paths,
            "video_paths": video_paths,
        }, product_id=product_id)

    def start_discovery(self, owner_id: str, space_id: str, payload: dict) -> dict:
        space = self.store.get_space(owner_id, space_id)
        keywords = list(payload.get("keywords") or [])
        if payload.get("product_id"):
            product = self.store.get_product(owner_id, space_id, payload["product_id"])
            keywords.extend(product["keywords"])
            if product["category"]:
                keywords.append(product["category"])
            if not keywords:
                keywords.append(product["title"])
        keywords.extend(space["keywords"])
        keywords = list(dict.fromkeys(value.strip() for value in keywords if value.strip()))[:5]
        if not keywords:
            raise OperationError("请先填写商品、账号关键词或本次搜索关键词")
        rules = ViralRules(
            keywords=keywords,
            hours=payload.get("hours", 72),
            max_followers=100_000,
            min_likes=0,
            min_interactions=300,
            min_ratio=0.05,
            pages=1,
            candidate_limit=60,
            limit=payload.get("limit", 20),
        )
        try:
            run = self.viral_service.submit(rules)
        except ViralError as error:
            raise OperationError(str(error)) from error
        return {"run": run, "keywords": keywords}

    def import_discovery(self, owner_id: str, space_id: str, run_id: str) -> dict:
        self.store.get_space(owner_id, space_id)
        try:
            run = self.viral_service.store.get_run(run_id)
        except KeyError as error:
            raise OperationError("爆款发现批次不存在") from error
        if run.get("state") not in {"success", "partial"}:
            raise OperationError("爆款发现尚未完成")
        imported = []
        for note in run.get("items", []):
            imported.append(self.store.upsert_note(owner_id, space_id, note | {
                "source_kind": "traffic_note",
                "body": note.get("description", ""),
                "image_urls": [note["cover"]] if note.get("cover") else [],
            }))
        return {"imported": len(imported), "notes": imported}

    def generate_video(self, owner_id: str, space_id: str, generation_id: str, request: dict) -> dict:
        product = self.store.get_product(owner_id, space_id, request["product_id"])
        notes = self.store.notes(owner_id, space_id, request["reference_note_ids"])
        context = self.store.prompt_context(owner_id, space_id, request["reference_note_ids"], request["product_id"])
        query = "\n".join([product["title"], product["description"], product["selling_points"], context])
        knowledge = self.knowledge.retrieve_for_creation(query, {"general", "note", "image"}, limit=10)
        knowledge_context = "\n\n".join(value for value in (self.knowledge.context(knowledge, query=query), context) if value)
        media_root = self.runtime.download_root().resolve()
        image_paths = [path for path in product["image_paths"] if (media_root / path).is_file()][:6]
        images = self.load_images(media_root, image_paths) if image_paths else []
        workflow_context = """你正在为一个指定的小红书运营账号制作可执行的视频笔记方案。
必须以当前商品资料为事实边界，以商品图片为主体身份；对标笔记只用于迁移开场停留点、叙事节奏、镜头职责和收尾方式。
严格贴合主对标的标题长度、段落/口播节奏和情绪密度，但不得复制连续原句，不得冒充对标作者或编造亲测、销量、价格、功效。
分镜必须能由已提供的商品图片或商品视频实际拍摄/剪辑完成；没有素材依据时写“需补拍”，不能假装已有素材。
只返回 JSON 对象，不要代码围栏：
{"title":"20字内标题","caption":"可直接发布的正文，含自然话题","hook":"前3秒钩子","duration_seconds":30,
"voiceover":"完整口播","shots":[{"seconds":"0-3","visual":"画面与机位","on_screen_text":"屏幕文字","voiceover":"本镜口播","asset_source":"商品图/商品视频/需补拍"}],
"benchmark_alignment":[{"note_id":"实际使用的对标note_id","borrowed":"迁移的结构或节奏","discarded":"明确未迁移的事实"}],
"production_checklist":["拍摄或剪辑注意事项"]}。shots 至少 6 项，benchmark_alignment 必须覆盖所有指定对标。"""
        workflow_context += (
            "\n本次文案策略："
            + {
                "2": "同品创新：保留成交逻辑与心理推进，重做第一屏、场景和信息组织。",
                "3": "跨品迁移：只迁移内容公式、说服机制和节奏，用当前商品事实重建。",
                "4": "定题真人种草：用生活记录、痛点场景或朋友聊天切口降低营销感。",
                "5": "场景化素人：约180字、三段式、第一人称日常场景，不伪造体验。",
            }[request.get("copywriting_mode", "2")]
        )
        charge_id = f"operation-video:{generation_id}"
        try:
            receipt = self.billing.consume(owner_id, "text", TEXT_COST, charge_id, {"space_id": space_id})
            generated = self.gateway.generate(
                _json([{"note_id": note["note_id"], "title": note["title"], "body": note["body"], "structure": note["structure"]} for note in notes]),
                request.get("instructions", ""),
                "rewrite",
                images,
                knowledge_context=knowledge_context,
                workflow_context=workflow_context,
            )
            result = parse_json_object(generated["text"])
            shots = result.get("shots")
            alignment = result.get("benchmark_alignment")
            if not isinstance(shots, list) or len(shots) < 6:
                raise OperationError("视频方案缺少完整分镜，本次点数已退回")
            expected = {note["note_id"] for note in notes if note["note_id"]}
            actual = {str(item.get("note_id") or "") for item in alignment or [] if isinstance(item, dict)}
            if expected and not expected.issubset(actual):
                raise OperationError("视频方案没有逐篇落实所选对标，本次点数已退回")
            result["model"] = generated["model"]
            result["billing"] = {key: value for key, value in receipt.items() if key != "usage"}
            media_task = self._submit_video_media(media_root, product, result)
            if media_task:
                result["media_task"] = media_task
            run_id = self.knowledge.record_run(
                owner_id,
                "operation-video",
                True,
                product["title"],
                request.get("instructions", ""),
                _json(result),
                [],
                [entry["id"] for entry in knowledge],
                generated["model"],
                {**request, "space_id": space_id, "generation_id": generation_id},
            )
            result["run_id"] = run_id
            return self.store.update_generation(
                owner_id,
                space_id,
                generation_id,
                status="success",
                title=str(result.get("title") or product["title"]),
                result=result,
            )
        except Exception as error:
            self.billing.refund(owner_id, charge_id)
            self.store.update_generation(owner_id, space_id, generation_id, status="failed", error=str(getattr(error, "detail", error)))
            raise

    def _submit_video_media(self, media_root: Path, product: dict, result: dict) -> dict:
        """Create a real draft video from product media without changing product identity."""
        def safe_paths(values, limit):
            paths = []
            for value in values:
                target = (media_root / value).resolve()
                if target.is_relative_to(media_root) and target.is_file():
                    paths.append(target)
                if len(paths) == limit:
                    break
            return paths

        video_paths = safe_paths(product.get("video_paths", []), 20)
        image_paths = safe_paths(product.get("image_paths", []), 12)
        try:
            if video_paths and self.remix_manager:
                task = self.remix_manager.submit(media_root, video_paths, speed=1.0)
                return {"kind": "product_video_remix", **task}
            if image_paths and self.slideshow_manager:
                target_seconds = float(result.get("duration_seconds") or 30)
                seconds = min(15.0, max(0.5, target_seconds / len(image_paths)))
                task = self.slideshow_manager.submit(
                    media_root, image_paths, seconds=seconds, music=None
                )
                return {"kind": "image_slideshow", **task}
        except Exception as error:
            return {"kind": "media_failed", "state": "failed", "error": str(error)}
        return {}

    def refresh_media_task(self, media_task: dict) -> dict:
        if not media_task or not media_task.get("task_id"):
            return media_task
        manager = (
            self.remix_manager
            if media_task.get("kind") == "product_video_remix"
            else self.slideshow_manager
        )
        if not manager:
            return media_task
        current = next(
            (task for task in manager.snapshot() if task.get("task_id") == media_task["task_id"]),
            None,
        )
        return {"kind": media_task.get("kind"), **current} if current else media_task


def parse_json_object(text: str) -> dict:
    value = str(text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value).strip()
    try:
        result = json.loads(value)
    except (TypeError, ValueError) as error:
        raise OperationError("AI 返回格式不是有效 JSON，本次点数已退回") from error
    if not isinstance(result, dict):
        raise OperationError("AI 返回的内容结构有误，本次点数已退回")
    return result


def public_reference(note: dict) -> dict:
    metrics = note["metrics"]
    return {
        "note_id": note["note_id"] or note["id"],
        "title": note["title"] or "无标题",
        "description": note["body"][:4_000],
        "tags": note["tags"][:30],
        "keywords": [],
        "likes": int(metrics.get("likes") or 0),
        "collects": int(metrics.get("collects") or 0),
        "comments": int(metrics.get("comments") or 0),
        "shares": int(metrics.get("shares") or 0),
        "interactions": int(metrics.get("interactions") or 0),
        "followers": metrics.get("followers"),
        "structure": note["structure"],
        "source_kind": note["source_kind"],
    }


def register_operation_routes(
    app,
    service: OperationService,
    rewrite_workflow,
    require_user,
    require_csrf,
    knowledge,
):
    store = service.store

    def detail_or_404(owner_id: str, space_id: str):
        try:
            result = store.detail(owner_id, space_id)
            rewrite_tasks = {task["id"]: task for task in rewrite_workflow.snapshot(owner_id)}
            for generation in result["generations"]:
                if generation["content_type"] == "video" and generation["result"].get("media_task"):
                    generation["result"]["media_task"] = service.refresh_media_task(
                        generation["result"]["media_task"]
                    )
                if generation["content_type"] != "graphic" or not generation["rewrite_job_ids"]:
                    continue
                jobs = [rewrite_tasks[job_id] for job_id in generation["rewrite_job_ids"] if job_id in rewrite_tasks]
                if not jobs:
                    continue
                if any(job["state"] in {"pending", "processing"} for job in jobs):
                    status = "processing"
                elif all(job["state"] == "success" for job in jobs):
                    status = "success"
                elif any(job.get("text") or job.get("outputs") for job in jobs):
                    status = "partial"
                else:
                    status = "failed"
                generation["status"] = status
                generation["result"] = {
                    **generation["result"],
                    "completed_articles": sum(job["state"] == "success" for job in jobs),
                    "article_count": len(jobs),
                    "completed_images": sum(len(job.get("outputs", [])) for job in jobs),
                }
            result["layers"] = {
                "base_knowledge": knowledge.stats(),
                "account_knowledge": {
                    "benchmark_accounts": len(result["benchmark_accounts"]),
                    "notes": len(result["notes"]),
                    "products": len(result["products"]),
                    "generations": len(result["generations"]),
                },
            }
            return result
        except KeyError as error:
            raise HTTPException(404, "账号空间不存在") from error

    @app.get("/api/operations/spaces")
    def list_spaces(user=Depends(require_user)):
        return {"spaces": store.spaces(user["id"]), "base_knowledge": knowledge.stats()}

    @app.post("/api/operations/spaces", status_code=201)
    def create_space(payload: SpaceInput, user=Depends(require_csrf)):
        return {"space": store.create_space(user["id"], payload.model_dump())}

    @app.get("/api/operations/spaces/{space_id}")
    def get_space(space_id: str, user=Depends(require_user)):
        return detail_or_404(user["id"], space_id)

    @app.put("/api/operations/spaces/{space_id}")
    def update_space(space_id: str, payload: SpaceInput, user=Depends(require_csrf)):
        try:
            return {"space": store.update_space(user["id"], space_id, payload.model_dump())}
        except KeyError as error:
            raise HTTPException(404, "账号空间不存在") from error

    @app.post("/api/operations/spaces/{space_id}/analyze-profile")
    def analyze_profile(space_id: str, user=Depends(require_csrf)):
        try:
            return service.analyze_profile(user["id"], space_id)
        except KeyError as error:
            raise HTTPException(404, "账号空间不存在") from error
        except QuotaExceeded as error:
            raise HTTPException(402, {"message": str(error), "usage": error.usage}) from error
        except (OperationError, BillingError) as error:
            raise HTTPException(422, str(error)) from error

    @app.delete("/api/operations/spaces/{space_id}", status_code=204)
    def delete_space(space_id: str, user=Depends(require_csrf)):
        try:
            store.delete_space(user["id"], space_id)
        except KeyError as error:
            raise HTTPException(404, "账号空间不存在") from error

    @app.post("/api/operations/spaces/{space_id}/benchmark-accounts", status_code=201)
    def add_account(space_id: str, payload: BenchmarkAccountInput, user=Depends(require_csrf)):
        try:
            return {"account": store.add_account(user["id"], space_id, payload.model_dump())}
        except KeyError as error:
            raise HTTPException(404, "账号空间不存在") from error

    @app.delete("/api/operations/spaces/{space_id}/benchmark-accounts/{account_id}", status_code=204)
    def delete_account(space_id: str, account_id: str, user=Depends(require_csrf)):
        try:
            store.delete_account(user["id"], space_id, account_id)
        except KeyError as error:
            raise HTTPException(404, "对标账号不存在") from error

    @app.post("/api/operations/spaces/{space_id}/benchmark-accounts/{account_id}/sync", status_code=202)
    def sync_account(space_id: str, account_id: str, user=Depends(require_csrf)):
        try:
            return {"job": service.submit_account_sync(user["id"], space_id, account_id)}
        except KeyError as error:
            raise HTTPException(404, "对标账号不存在") from error
        except OperationError as error:
            raise HTTPException(409, str(error)) from error

    @app.get("/api/operations/sync-jobs/{job_id}")
    def sync_job(job_id: str, user=Depends(require_user)):
        try:
            return {"job": service.job(user["id"], job_id)}
        except KeyError as error:
            raise HTTPException(404, "采集任务不存在") from error

    @app.post("/api/operations/spaces/{space_id}/benchmark-notes", status_code=201)
    def add_note(space_id: str, payload: BenchmarkNoteInput, user=Depends(require_csrf)):
        try:
            return {"note": service.import_manual_note(user["id"], space_id, payload.content)}
        except KeyError as error:
            raise HTTPException(404, "账号空间不存在") from error
        except (OperationError, ValueError) as error:
            raise HTTPException(422, str(error)) from error

    @app.delete("/api/operations/spaces/{space_id}/notes/{note_id}", status_code=204)
    def delete_note(space_id: str, note_id: str, user=Depends(require_csrf)):
        try:
            store.delete_note(user["id"], space_id, note_id)
        except KeyError as error:
            raise HTTPException(404, "笔记不存在") from error

    @app.post("/api/operations/spaces/{space_id}/products", status_code=201)
    def add_product(space_id: str, payload: ProductInput, user=Depends(require_csrf)):
        try:
            return {"product": service.import_product(user["id"], space_id, payload.model_dump())}
        except KeyError as error:
            raise HTTPException(404, "账号空间不存在") from error
        except OperationError as error:
            raise HTTPException(422, str(error)) from error

    @app.delete("/api/operations/spaces/{space_id}/products/{product_id}", status_code=204)
    def delete_product(space_id: str, product_id: str, user=Depends(require_csrf)):
        try:
            store.delete_product(user["id"], space_id, product_id)
        except KeyError as error:
            raise HTTPException(404, "商品不存在") from error

    @app.post("/api/operations/spaces/{space_id}/discover", status_code=202)
    def discover(space_id: str, payload: DiscoveryInput, user=Depends(require_csrf)):
        try:
            return service.start_discovery(user["id"], space_id, payload.model_dump())
        except KeyError as error:
            raise HTTPException(404, "账号空间或商品不存在") from error
        except OperationError as error:
            raise HTTPException(409, str(error)) from error

    @app.post("/api/operations/spaces/{space_id}/discover/{run_id}/import")
    def import_discovery(space_id: str, run_id: str, user=Depends(require_csrf)):
        try:
            return service.import_discovery(user["id"], space_id, run_id)
        except KeyError as error:
            raise HTTPException(404, "账号空间不存在") from error
        except OperationError as error:
            raise HTTPException(409, str(error)) from error

    @app.post("/api/operations/spaces/{space_id}/generate", status_code=202)
    def generate(space_id: str, payload: OperationGenerateInput, user=Depends(require_csrf)):
        request = payload.model_dump()
        try:
            product = store.get_product(user["id"], space_id, request["product_id"])
            notes = store.notes(user["id"], space_id, request["reference_note_ids"])
            if not notes:
                raise OperationError("至少选择一篇对标笔记")
            generation = store.create_generation(user["id"], space_id, request)
            if request["content_type"] == "video":
                return {"generation": service.generate_video(user["id"], space_id, generation["id"], request)}
            if not product["image_paths"]:
                store.update_generation(user["id"], space_id, generation["id"], status="failed", error="商品没有本地原图")
                raise OperationError("图文生成必须先从商品素材库导入带原图的商品")
            primary = notes[0]
            if not primary["url"]:
                raise OperationError("主对标笔记缺少原始链接，请选择可访问的笔记")
            operation_context = store.prompt_context(
                user["id"], space_id, request["reference_note_ids"], request["product_id"]
            )
            product_facts = "\n".join(value for value in (
                f"商品名称：{product['title']}",
                f"商品资料：{product['description']}" if product["description"] else "",
                f"真实卖点：{product['selling_points']}" if product["selling_points"] else "",
                f"商品分类：{product['category']}" if product["category"] else "",
            ) if value)
            rewrite_request = {
                "content": primary["url"],
                "style": request["style"],
                "image_count": request["image_count"],
                "article_count": request["article_count"],
                "product_facts": product_facts,
                "target_audience": product["target_audience"] or store.get_space(user["id"], space_id)["target_audience"],
                "instructions": request["instructions"],
                "corpus_ids": [],
                "image_size": "1024x1536",
                "image_quality": "medium",
                "request_id": "operation-" + generation["id"],
                "operation_space_id": space_id,
                "operation_generation_id": generation["id"],
                "operation_context": operation_context,
                "operation_references": [public_reference(note) for note in notes],
                "copywriting_mode": request["copywriting_mode"],
                "subject_image_paths": product["image_paths"][:6],
            }
            batch = rewrite_workflow.submit(rewrite_request, user["id"])
            job_ids = [job["id"] for job in batch["jobs"]]
            generation = store.update_generation(
                user["id"],
                space_id,
                generation["id"],
                status="processing",
                title=f"{product['title']} · 图文",
                rewrite_job_ids=job_ids,
                result={"batch_id": batch["batch_id"], "article_count": batch["article_count"]},
            )
            return {"generation": generation, "rewrite": batch}
        except KeyError as error:
            raise HTTPException(404, "账号空间、商品或对标笔记不存在") from error
        except QuotaExceeded as error:
            raise HTTPException(402, {"message": str(error), "usage": error.usage}) from error
        except (OperationError, ValueError, BillingError, KnowledgeBaseError) as error:
            raise HTTPException(422, str(error)) from error
