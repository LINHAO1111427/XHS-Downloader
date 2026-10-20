"""Durable response replay and charge recovery for synchronous AI requests."""

from contextvars import ContextVar
from hashlib import sha256
import json
from time import time

from billing import BillingConflict


current_operation: ContextVar[str] = ContextVar("billing_operation", default="")


class RequestAccounting:
    def __init__(self, billing):
        self.billing = billing
        with billing._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS api_requests (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('running','complete','interrupted')),
                    status INTEGER, response TEXT, created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS api_request_charges (
                    request_id TEXT PRIMARY KEY, operation_id TEXT NOT NULL,
                    user_id TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS api_request_charges_operation
                    ON api_request_charges(operation_id);
            """)

    def begin(self, user_id, key, path, body):
        if not key or len(key) > 128 or not key.isascii() or not key.isprintable():
            raise ValueError("请提供有效的 Idempotency-Key")
        operation_id = sha256(f"{user_id}\0{key}".encode()).hexdigest()
        fingerprint = sha256(path.encode() + b"\0" + body).hexdigest()
        with self.billing._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM api_requests WHERE id=?", (operation_id,)
            ).fetchone()
            if row:
                if row["fingerprint"] != fingerprint:
                    raise BillingConflict("请求标识与原请求内容不一致")
                return operation_id, dict(row)
            db.execute(
                "INSERT INTO api_requests(id,user_id,fingerprint,state,created_at) VALUES(?,?,?,'running',?)",
                (operation_id, user_id, fingerprint, int(time())),
            )
            db.commit()
        return operation_id, None

    def refund(self, operation_id):
        with self.billing._connection() as db:
            rows = db.execute(
                "SELECT user_id,request_id FROM api_request_charges WHERE operation_id=?",
                (operation_id,),
            ).fetchall()
        for row in rows:
            self.billing.refund(row["user_id"], row["request_id"])

    def finish(self, operation_id, status, body):
        # A failed response is replayed too: retries never repeat the side effect.
        if status >= 400:
            self.refund(operation_id)
        with self.billing._connection() as db:
            db.execute(
                "UPDATE api_requests SET state='complete',status=?,response=? WHERE id=? AND state='running'",
                (status, body.decode("utf-8"), operation_id),
            )
            db.commit()

    def recover(self):
        # Called once while holding the exclusive server lock, before serving.
        with self.billing._connection() as db:
            rows = db.execute(
                "SELECT id FROM api_requests WHERE state='running'"
            ).fetchall()
        for row in rows:
            self.refund(row["id"])
            with self.billing._connection() as db:
                db.execute(
                    "UPDATE api_requests SET state='interrupted',status=409,response=? WHERE id=?",
                    (
                        json.dumps(
                            {
                                "detail": "服务重启中断了该请求，点数已退回；请重新发起生成",
                                "code": "request_interrupted",
                            },
                            ensure_ascii=False,
                        ),
                        row["id"],
                    ),
                )
                db.commit()
        return len(rows)
