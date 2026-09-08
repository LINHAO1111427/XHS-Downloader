"""Usage accounting and payment-ready credit ledger for AI generation."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import time
from typing import Iterator
from uuid import uuid4


CST = timezone(timedelta(hours=8))
TEXT_COST = 1
IMAGE_COST = 5

DEFAULT_PLANS = (
    {
        "id": "free",
        "name": "每日免费",
        "daily_free_units": 20,
        "credits": 0,
        "price_cents": 0,
        "description": "每天 20 点，文本生成 20 次或图片生成 4 次",
    },
    {
        "id": "starter",
        "name": "轻量包",
        "daily_free_units": 0,
        "credits": 100,
        "price_cents": 990,
        "description": "100 点，用完再买，不自动续费",
    },
    {
        "id": "pro",
        "name": "创作包",
        "daily_free_units": 0,
        "credits": 500,
        "price_cents": 2990,
        "description": "500 点，适合持续创作",
    },
    {
        "id": "scale",
        "name": "团队包",
        "daily_free_units": 0,
        "credits": 2000,
        "price_cents": 9900,
        "description": "2000 点，适合批量使用",
    },
)


class BillingError(ValueError):
    pass


class QuotaExceeded(BillingError):
    def __init__(self, usage: dict):
        super().__init__("今日免费点数已用完，请充值后继续生成")
        self.usage = usage


class BillingStore:
    """SQLite-backed credits with atomic consumption and idempotency."""

    def __init__(self, path: Path, *, plans: tuple[dict, ...] = DEFAULT_PLANS):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.plans = plans
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
                CREATE TABLE IF NOT EXISTS billing_plans (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    daily_free_units INTEGER NOT NULL DEFAULT 0,
                    credits INTEGER NOT NULL DEFAULT 0,
                    price_cents INTEGER NOT NULL DEFAULT 0,
                    description TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS billing_accounts (
                    user_id TEXT PRIMARY KEY,
                    paid_credits INTEGER NOT NULL DEFAULT 0 CHECK (paid_credits >= 0),
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS billing_daily_usage (
                    user_id TEXT NOT NULL,
                    usage_date TEXT NOT NULL,
                    free_used INTEGER NOT NULL DEFAULT 0 CHECK (free_used >= 0),
                    paid_used INTEGER NOT NULL DEFAULT 0 CHECK (paid_used >= 0),
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (user_id, usage_date)
                );
                CREATE TABLE IF NOT EXISTS billing_ledger (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    request_id TEXT NOT NULL UNIQUE,
                    entry_type TEXT NOT NULL CHECK (entry_type IN ('consume', 'refund', 'grant')),
                    feature TEXT NOT NULL,
                    units INTEGER NOT NULL CHECK (units > 0),
                    free_units INTEGER NOT NULL DEFAULT 0 CHECK (free_units >= 0),
                    paid_units INTEGER NOT NULL DEFAULT 0 CHECK (paid_units >= 0),
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS billing_ledger_user_created
                    ON billing_ledger(user_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS billing_orders (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL REFERENCES billing_plans(id),
                    amount_cents INTEGER NOT NULL,
                    credits INTEGER NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'unconfigured',
                    status TEXT NOT NULL CHECK (status IN ('pending', 'paid', 'cancelled', 'failed')),
                    provider_order_id TEXT UNIQUE,
                    created_at INTEGER NOT NULL,
                    paid_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS billing_orders_user_created
                    ON billing_orders(user_id, created_at DESC);
                """
            )
            now = int(time())
            for plan in self.plans:
                connection.execute(
                    """
                    INSERT INTO billing_plans(
                        id, name, daily_free_units, credits, price_cents,
                        description, active, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(id) DO NOTHING
                    """,
                    (
                        plan["id"],
                        plan["name"],
                        plan["daily_free_units"],
                        plan["credits"],
                        plan["price_cents"],
                        plan["description"],
                        now,
                        now,
                    ),
                )
            connection.commit()
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    @staticmethod
    def _date(now: int | float | None = None) -> str:
        return datetime.fromtimestamp(now or time(), CST).date().isoformat()

    def _free_limit(self, connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT daily_free_units FROM billing_plans WHERE id='free' AND active=1"
        ).fetchone()
        return int(row[0]) if row else 0

    def _ensure_account(self, connection: sqlite3.Connection, user_id: str, now: int) -> None:
        connection.execute(
            "INSERT OR IGNORE INTO billing_accounts(user_id, paid_credits, updated_at) VALUES (?, 0, ?)",
            (user_id, now),
        )

    def _usage_in_transaction(self, connection: sqlite3.Connection, user_id: str, now: int) -> dict:
        date = self._date(now)
        self._ensure_account(connection, user_id, now)
        daily = connection.execute(
            "SELECT free_used, paid_used FROM billing_daily_usage WHERE user_id=? AND usage_date=?",
            (user_id, date),
        ).fetchone()
        account = connection.execute(
            "SELECT paid_credits FROM billing_accounts WHERE user_id=?", (user_id,)
        ).fetchone()
        free_used = int(daily[0]) if daily else 0
        paid_used = int(daily[1]) if daily else 0
        free_limit = self._free_limit(connection)
        paid_credits = int(account[0]) if account else 0
        return {
            "usage_date": date,
            "daily_free_units": free_limit,
            "free_used": free_used,
            "free_remaining": max(0, free_limit - free_used),
            "paid_credits": paid_credits,
            "paid_used_today": paid_used,
            "available_units": max(0, free_limit - free_used) + paid_credits,
            "costs": {"text": TEXT_COST, "image": IMAGE_COST},
        }

    def usage(self, user_id: str, now: int | float | None = None) -> dict:
        timestamp = int(now or time())
        with self._connection() as connection:
            return self._usage_in_transaction(connection, user_id, timestamp)

    def plans_payload(self) -> list[dict]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id, name, daily_free_units, credits, price_cents, description FROM billing_plans WHERE active=1 ORDER BY price_cents, credits"
            ).fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "daily_free_units": row["daily_free_units"],
                "credits": row["credits"],
                "price_cents": row["price_cents"],
                "price": f"{row['price_cents'] / 100:.2f}",
                "description": row["description"],
            }
            for row in rows
        ]

    def consume(self, user_id: str, feature: str, units: int, request_id: str, metadata: dict | None = None) -> dict:
        if not user_id or not request_id or len(request_id) > 160:
            raise BillingError("计费请求标识无效")
        if units <= 0 or units > 100:
            raise BillingError("计费点数无效")
        now = int(time())
        date = self._date(now)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT id, units, free_units, paid_units FROM billing_ledger WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if existing:
                connection.commit()
                usage = self._usage_in_transaction(connection, user_id, now)
                return {
                    "ledger_id": str(existing[0]),
                    "request_id": request_id,
                    "units": int(existing[1]),
                    "free_units": int(existing[2]),
                    "paid_units": int(existing[3]),
                    "status": "already_consumed",
                    "usage": usage,
                }
            usage = self._usage_in_transaction(connection, user_id, now)
            if usage["available_units"] < units:
                connection.rollback()
                raise QuotaExceeded(usage)
            free_units = min(units, usage["free_remaining"])
            paid_units = units - free_units
            connection.execute(
                """
                INSERT INTO billing_daily_usage(user_id, usage_date, free_used, paid_used, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, usage_date) DO UPDATE SET
                    free_used=free_used + excluded.free_used,
                    paid_used=paid_used + excluded.paid_used,
                    updated_at=excluded.updated_at
                """,
                (user_id, date, free_units, paid_units, now),
            )
            connection.execute(
                "UPDATE billing_accounts SET paid_credits=paid_credits-?, updated_at=? WHERE user_id=?",
                (paid_units, now, user_id),
            )
            ledger_id = uuid4().hex
            connection.execute(
                """
                INSERT INTO billing_ledger(
                    id, user_id, request_id, entry_type, feature, units,
                    free_units, paid_units, metadata, created_at
                ) VALUES (?, ?, ?, 'consume', ?, ?, ?, ?, ?, ?)
                """,
                (ledger_id, user_id, request_id, feature, units, free_units, paid_units, _json(metadata), now),
            )
            connection.commit()
            return {
                "ledger_id": ledger_id,
                "request_id": request_id,
                "units": units,
                "free_units": free_units,
                "paid_units": paid_units,
                "status": "consumed",
                "usage": self._usage_in_transaction(connection, user_id, now),
            }

    def refund(self, user_id: str, request_id: str) -> bool:
        now = int(time())
        refund_request = f"refund:{request_id}"
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM billing_ledger WHERE request_id=?", (refund_request,)).fetchone():
                connection.commit()
                return False
            original = connection.execute(
                "SELECT units, free_units, paid_units, feature, created_at FROM billing_ledger WHERE user_id=? AND request_id=? AND entry_type='consume'",
                (user_id, request_id),
            ).fetchone()
            if not original:
                connection.rollback()
                return False
            free_units, paid_units = int(original[1]), int(original[2])
            original_date = self._date(int(original[4]))
            connection.execute(
                "UPDATE billing_daily_usage SET free_used=max(0, free_used-?), paid_used=max(0, paid_used-?), updated_at=? WHERE user_id=? AND usage_date=?",
                (free_units, paid_units, now, user_id, original_date),
            )
            connection.execute(
                "UPDATE billing_accounts SET paid_credits=paid_credits+?, updated_at=? WHERE user_id=?",
                (paid_units, now, user_id),
            )
            connection.execute(
                """
                INSERT INTO billing_ledger(
                    id, user_id, request_id, entry_type, feature, units,
                    free_units, paid_units, metadata, created_at
                ) VALUES (?, ?, ?, 'refund', ?, ?, ?, ?, '{}', ?)
                """,
                (uuid4().hex, user_id, refund_request, str(original[3]), int(original[0]), free_units, paid_units, now),
            )
            connection.commit()
            return True

    def grant(self, user_id: str, units: int, source: str = "admin") -> dict:
        if units <= 0 or units > 1_000_000:
            raise BillingError("充值点数无效")
        now = int(time())
        request_id = f"grant:{uuid4().hex}"
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_account(connection, user_id, now)
            connection.execute(
                "UPDATE billing_accounts SET paid_credits=paid_credits+?, updated_at=? WHERE user_id=?",
                (units, now, user_id),
            )
            ledger_id = uuid4().hex
            connection.execute(
                "INSERT INTO billing_ledger(id,user_id,request_id,entry_type,feature,units,paid_units,metadata,created_at) VALUES (?, ?, ?, 'grant', ?, ?, ?, ?, ?)",
                (ledger_id, user_id, request_id, source, units, units, _json({"source": source}), now),
            )
            connection.commit()
            return {"ledger_id": ledger_id, "units": units, "usage": self._usage_in_transaction(connection, user_id, now)}

    def create_order(self, user_id: str, plan_id: str) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id, price_cents, credits FROM billing_plans WHERE id=? AND active=1 AND price_cents>0",
                (plan_id,),
            ).fetchone()
        plan = dict(row) if row else None
        if not plan:
            raise BillingError("套餐不存在或无需购买")
        order_id = uuid4().hex
        now = int(time())
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO billing_orders(id,user_id,plan_id,amount_cents,credits,status,created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                (order_id, user_id, plan_id, plan["price_cents"], plan["credits"], now),
            )
            connection.commit()
        return {"id": order_id, "plan_id": plan_id, "amount_cents": plan["price_cents"], "credits": plan["credits"], "status": "pending", "provider": "unconfigured"}


def _json(value: dict | None) -> str:
    import json

    return json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"))
