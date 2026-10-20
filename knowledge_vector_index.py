"""Deterministic local vector index for knowledge-first content creation.

The index is deliberately local and reproducible: it uses hashed word and
Chinese character n-gram features, so creation never depends on a remote
embedding service or a model download.  Exact keyword ranking remains in
place; cosine similarity supplies the semantic ordering signal between them.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from time import time
from typing import Iterable

VECTOR_VERSION = 1
VECTOR_DIM = 256


def _tokens(text: str) -> list[str]:
    value = str(text or "").casefold()
    result: list[str] = []
    for token in re.findall(r"[a-z0-9][a-z0-9_-]+|[\u4e00-\u9fff]+", value):
        result.append(token)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            result.extend(token[index : index + 2] for index in range(len(token) - 1))
    return result


def _index(token: str, salt: str = "") -> tuple[int, float]:
    digest = hashlib.sha256((salt + token).encode("utf-8")).digest()
    position = int.from_bytes(digest[:4], "big") % VECTOR_DIM
    sign = 1.0 if digest[4] & 1 else -1.0
    return position, sign


def vectorize(text: str) -> list[float]:
    vector = [0.0] * VECTOR_DIM
    tokens = _tokens(text)
    if not tokens:
        return vector
    for token in tokens:
        position, sign = _index(token)
        vector[position] += sign
        # A second independent bucket reduces collisions for short Chinese terms.
        position2, sign2 = _index(token, "#")
        vector[position2] += sign2 * 0.5
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [value / norm for value in vector]
    return vector


def cosine(left: Iterable[float], right: Iterable[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _entry_text(row: sqlite3.Row | dict) -> str:
    tags = row["tags"] if isinstance(row, sqlite3.Row) else row.get("tags", "[]")
    if not isinstance(tags, str):
        tags = json.dumps(tags, ensure_ascii=False)
    title = row["title"] if isinstance(row, sqlite3.Row) else row.get("title", "")
    content = row["content"] if isinstance(row, sqlite3.Row) else row.get("content", "")
    return f"{title}\n{tags}\n{content}"


def source_digest(row: sqlite3.Row | dict) -> str:
    return hashlib.sha256(_entry_text(row).encode("utf-8")).hexdigest()


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_vectors (
            entry_id TEXT PRIMARY KEY REFERENCES knowledge_entries(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            dimensions INTEGER NOT NULL,
            vector TEXT NOT NULL,
            source_digest TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS knowledge_vectors_version ON knowledge_vectors(version)"
    )


def upsert_vector(connection: sqlite3.Connection, row: sqlite3.Row | dict) -> None:
    digest = source_digest(row)
    values = vectorize(_entry_text(row))
    entry_id = row["id"] if isinstance(row, sqlite3.Row) else row.get("id")
    connection.execute(
        """
        INSERT INTO knowledge_vectors(entry_id, version, dimensions, vector, source_digest, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(entry_id) DO UPDATE SET
            version=excluded.version, dimensions=excluded.dimensions,
            vector=excluded.vector, source_digest=excluded.source_digest,
            updated_at=excluded.updated_at
        """,
        (str(entry_id), VECTOR_VERSION, VECTOR_DIM, json.dumps(values), digest, int(time())),
    )


def rebuild(connection: sqlite3.Connection, *, only_missing: bool = False) -> int:
    ensure_schema(connection)
    rows = connection.execute("SELECT * FROM knowledge_entries WHERE active=1").fetchall()
    count = 0
    for row in rows:
        existing = connection.execute(
            "SELECT source_digest, version FROM knowledge_vectors WHERE entry_id=?",
            (row["id"],),
        ).fetchone()
        if only_missing and existing and existing["source_digest"] == source_digest(row) and existing["version"] == VECTOR_VERSION:
            continue
        upsert_vector(connection, row)
        count += 1
    # Inactive entries do not participate in retrieval and should not leave stale rows.
    connection.execute(
        "DELETE FROM knowledge_vectors WHERE entry_id NOT IN (SELECT id FROM knowledge_entries WHERE active=1)"
    )
    return count


def rank(connection: sqlite3.Connection, query: str, kinds: set[str], limit: int = 12) -> dict[str, float]:
    ensure_schema(connection)
    wanted = {str(kind) for kind in kinds}
    query_vector = vectorize(query)
    rows = connection.execute(
        """
        SELECT v.entry_id, v.vector, k.kind
        FROM knowledge_vectors v JOIN knowledge_entries k ON k.id=v.entry_id
        WHERE k.active=1 AND v.version=?
        """,
        (VECTOR_VERSION,),
    ).fetchall()
    scores: list[tuple[float, str]] = []
    for row in rows:
        if row["kind"] not in wanted:
            continue
        try:
            value = cosine(query_vector, json.loads(row["vector"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            value = 0.0
        scores.append((value, str(row["entry_id"])))
    scores.sort(reverse=True)
    return {entry_id: score for score, entry_id in scores[: max(1, min(int(limit), 50))]}

