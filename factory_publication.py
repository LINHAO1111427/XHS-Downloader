"""Explicit publication marks and account-scoped, server-side content paging."""
from __future__ import annotations

from datetime import date
from time import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PublicationStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["published", "unpublished"]


class RunQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: date | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)
    status: Literal["", "published", "unpublished", "ready", "working", "draft"] = ""
    content_filter: Literal["", "graphic", "video", "draft", "published", "awaiting_metrics"] = ""
    completion: Literal["", "finished", "unfinished"] = ""
    search: str = Field(default="", max_length=200)


def initialize(operations):
    with operations.connection() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS factory_publication_status (
            run_id TEXT PRIMARY KEY REFERENCES factory_runs(id) ON DELETE CASCADE,
            is_published INTEGER NOT NULL CHECK(is_published IN (0,1)),
            updated_at REAL NOT NULL)""")


def published_sql(alias="r"):
    # Aliases are fixed by our callers; user input is always passed as parameters.
    return f"""COALESCE((SELECT s.is_published FROM factory_publication_status s WHERE s.run_id={alias}.id),
        CASE WHEN {alias}.state='published' OR {alias}.published_url<>'' OR
        EXISTS(SELECT 1 FROM factory_publications p WHERE p.run_id={alias}.id) THEN 1 ELSE 0 END)"""


def write_mark(db, run_id, published):
    db.execute("""INSERT INTO factory_publication_status(run_id,is_published,updated_at) VALUES(?,?,?)
        ON CONFLICT(run_id) DO UPDATE SET is_published=excluded.is_published,updated_at=excluded.updated_at""",
        (run_id, int(published), time()))


def protected_publication(db, run_id):
    """Keep historical registered publications and currently marked posts immutable to generation."""
    return db.execute("""SELECT 1 FROM factory_publications WHERE run_id=?
        UNION ALL SELECT 1 FROM factory_publication_status WHERE run_id=? AND is_published=1 LIMIT 1""",
        (run_id, run_id)).fetchone()


def set_status(store, owner, space, run_id, payload):
    from factory_learning import enrich
    value = PublicationStatusInput.model_validate(payload)
    store.run(owner, space, run_id)  # Enforce account/owner scope before mutation.
    with store.operations.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute("SELECT state,json_extract(plan,'$.title') AS title FROM factory_runs WHERE id=? AND space_id=?",
                             (run_id, space)).fetchone()
        if not current:
            raise KeyError(run_id)
        if value.status == "published" and (current["state"] not in {"draft", "ready", "published", "needs_review"}
                                            or not current["title"]):
            raise ValueError("请先完成文案，再标记已发布")
        write_mark(db, run_id, value.status == "published")
        db.execute("UPDATE factory_runs SET updated_at=? WHERE id=?", (time(), run_id))
    # A mark does not invent an actual publication date or remove saved measurements.
    return enrich(store.operations, [store.run(owner, space, run_id)])[0]


def enrich_flags(operations, runs):
    if not runs:
        return runs
    ids = [r["id"] for r in runs]
    with operations.connection() as db:
        flags = {r["run_id"]: bool(r["is_published"]) for r in db.execute(
            "SELECT run_id,is_published FROM factory_publication_status WHERE run_id IN (" + ",".join("?" for _ in ids) + ")", ids)}
    for run in runs:
        value = flags.get(run["id"], bool(run.get("publication") or run.get("published_url") or run["state"] == "published"))
        run["is_published"] = value
        run["publication_status"] = "published" if value else "unpublished"
    return runs


def list_runs(store, owner, space, query, *, delivery="package_path"):
    from account_factory import unpack
    from factory_learning import enrich, today
    query = RunQuery.model_validate(query)
    store.space(owner, space)
    available = "r.outputs<>'[]'" if delivery == "outputs" else "r.package_path<>''"
    finished = f"(r.state IN ('ready','published') AND {available})"
    published = published_sql()
    bucket = f"CASE WHEN {published}=1 THEN 'published' WHEN r.state='draft' THEN 'draft' WHEN {finished} THEN 'ready' ELSE 'working' END"
    where, params = ["r.space_id=?"], [space]
    if query.day:
        where.append("r.day=?")
        params.append(query.day.isoformat())
    scoped_where, scoped_params = " AND ".join(where), params.copy()
    if query.status in {"published", "unpublished"}:
        where.append(f"{published}=?")
        params.append(int(query.status == "published"))
    elif query.status:
        where.append(f"({bucket})=?")
        params.append(query.status)
    if query.content_filter in {"graphic", "video"}:
        where.append("r.content_type=?")
        params.append(query.content_filter)
    elif query.content_filter == "draft":
        where.append("r.state='draft'")
    elif query.content_filter in {"published", "awaiting_metrics"}:
        where.append(f"{published}=1")
        if query.content_filter == "awaiting_metrics":
            where.append("NOT EXISTS(SELECT 1 FROM factory_metric_snapshots m WHERE m.run_id=r.id AND m.observed_on=?)")
            params.append(today().isoformat())
    if query.completion:
        where.append(finished if query.completion == "finished" else f"NOT {finished}")
    if query.search.strip():
        where.append("instr(lower(COALESCE(json_extract(r.plan,'$.title'),'') || ' ' || COALESCE(json_extract(r.plan,'$.body'),'')),?)>0")
        params.append(query.search.strip().lower())
    condition = " AND ".join(where)
    with store.operations.connection() as db:
        db.execute("BEGIN")  # Count and page use the same SQLite read snapshot.
        counts = {r["bucket"]: r["total"] for r in db.execute(
            f"SELECT {bucket} AS bucket,COUNT(*) AS total FROM factory_runs r WHERE {scoped_where} GROUP BY bucket", scoped_params)}
        total = db.execute(f"SELECT COUNT(*) FROM factory_runs r WHERE {condition}", params).fetchone()[0]
        pages = max(1, (total + query.page_size - 1) // query.page_size)
        page = min(query.page, pages)
        rows = db.execute(f"SELECT r.* FROM factory_runs r WHERE {condition} ORDER BY r.day DESC,r.created_at DESC,r.id LIMIT ? OFFSET ?",
                          [*params, query.page_size, (page - 1) * query.page_size]).fetchall()
    overview = {key: counts.get(key, 0) for key in ("ready", "published", "working", "draft")}
    overview["unpublished"] = sum(overview[k] for k in ("ready", "working", "draft"))
    return {"runs": enrich(store.operations, [unpack(r) for r in rows]), "overview": overview,
            "pagination": {"page": page, "page_size": query.page_size, "total": total, "total_pages": pages}}
