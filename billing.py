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


class BillingConflict(BillingError):
    """An idempotency key was reused for a different or refunded operation."""


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
        self.unlimited_user_ids: set[str] = set()
        self._initialize()

    def set_unlimited_users(self, user_ids: set[str]) -> None:
        self.unlimited_user_ids = {str(user_id) for user_id in user_ids if user_id}

    def is_unlimited(self, user_id: str) -> bool:
        return user_id in self.unlimited_user_ids

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
                CREATE TABLE IF NOT EXISTS billing_order_requests (
                    user_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    order_id TEXT NOT NULL REFERENCES billing_orders(id),
                    PRIMARY KEY(user_id, request_id)
                );
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
        return (
            datetime.fromtimestamp(time() if now is None else now, CST)
            .date()
            .isoformat()
        )

    def _free_limit(self, connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT daily_free_units FROM billing_plans WHERE id='free' AND active=1"
        ).fetchone()
        return int(row[0]) if row else 0

    def _ensure_account(
        self, connection: sqlite3.Connection, user_id: str, now: int
    ) -> None:
        connection.execute(
            "INSERT OR IGNORE INTO billing_accounts(user_id, paid_credits, updated_at) VALUES (?, 0, ?)",
            (user_id, now),
        )

    def _usage_in_transaction(
        self, connection: sqlite3.Connection, user_id: str, now: int
    ) -> dict:
        date = self._date(now)
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
            "unlimited": self.is_unlimited(user_id),
            "costs": {"text": TEXT_COST, "image": IMAGE_COST},
        }

    def usage(self, user_id: str, now: int | float | None = None) -> dict:
        timestamp = int(time() if now is None else now)
        with self._connection() as connection:
            usage = self._usage_in_transaction(connection, user_id, timestamp)
            connection.commit()
            return usage

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

    def consume(
        self,
        user_id: str,
        feature: str,
        units: int,
        request_id: str,
        metadata: dict | None = None,
    ) -> dict:
        if (
            not user_id
            or not request_id
            or len(request_id) > 160
            or request_id.startswith(("refund:", "grant:", "payment:"))
        ):
            raise BillingError("计费请求标识无效")
        if type(units) is not int or units <= 0 or units > 100:
            raise BillingError("计费点数无效")
        now = int(time())
        date = self._date(now)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM billing_ledger WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if existing:
                if (
                    existing["user_id"],
                    existing["feature"],
                    existing["units"],
                    existing["entry_type"],
                ) != (user_id, feature, units, "consume"):
                    raise BillingConflict("请求标识已用于其他计费操作")
                if connection.execute(
                    "SELECT 1 FROM billing_ledger WHERE request_id=?",
                    (f"refund:{request_id}",),
                ).fetchone():
                    raise BillingConflict("该请求已退款，请使用新的请求标识重试")
                usage = self._usage_in_transaction(connection, user_id, now)
                connection.commit()
                return {
                    "ledger_id": str(existing["id"]),
                    "request_id": request_id,
                    "units": int(existing["units"]),
                    "free_units": int(existing["free_units"]),
                    "paid_units": int(existing["paid_units"]),
                    "status": "already_consumed",
                    "usage": usage,
                }
            usage = self._usage_in_transaction(connection, user_id, now)
            if self.is_unlimited(user_id):
                connection.commit()
                return {
                    "ledger_id": f"unlimited:{request_id}",
                    "request_id": request_id,
                    "units": units,
                    "free_units": 0,
                    "paid_units": 0,
                    "status": "unlimited",
                    "usage": usage,
                }
            if usage["available_units"] < units:
                connection.rollback()
                raise QuotaExceeded(usage)
            self._ensure_account(connection, user_id, now)
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
                (
                    ledger_id,
                    user_id,
                    request_id,
                    feature,
                    units,
                    free_units,
                    paid_units,
                    _json(metadata),
                    now,
                ),
            )
            from request_accounting import current_operation

            operation_id = current_operation.get()
            if operation_id:
                connection.execute(
                    "INSERT INTO api_request_charges(request_id,operation_id,user_id) VALUES(?,?,?)",
                    (request_id, operation_id, user_id),
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
            if connection.execute(
                "SELECT 1 FROM billing_ledger WHERE request_id=?", (refund_request,)
            ).fetchone():
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
                (
                    uuid4().hex,
                    user_id,
                    refund_request,
                    str(original[3]),
                    int(original[0]),
                    free_units,
                    paid_units,
                    now,
                ),
            )
            connection.commit()
            return True

    def grant(
        self,
        user_id: str,
        units: int,
        source: str = "admin",
        *,
        request_id: str | None = None,
        actor_id: str = "",
    ) -> dict:
        if not user_id or type(units) is not int or units <= 0 or units > 1_000_000:
            raise BillingError("充值点数无效")
        now = int(time())
        if request_id is not None and (not request_id or len(request_id) > 128):
            raise BillingError("充值请求标识无效")
        request_id = f"grant:{request_id or uuid4().hex}"
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM billing_ledger WHERE request_id=?", (request_id,)
            ).fetchone()
            metadata = _json({"source": source, "actor_id": actor_id})
            if existing:
                if (
                    existing["user_id"],
                    existing["units"],
                    existing["feature"],
                    existing["metadata"],
                ) != (user_id, units, source, metadata):
                    raise BillingConflict("充值请求标识已用于其他操作")
                return {
                    "ledger_id": existing["id"],
                    "units": units,
                    "status": "already_granted",
                    "usage": self._usage_in_transaction(connection, user_id, now),
                }
            self._ensure_account(connection, user_id, now)
            connection.execute(
                "UPDATE billing_accounts SET paid_credits=paid_credits+?, updated_at=? WHERE user_id=?",
                (units, now, user_id),
            )
            ledger_id = uuid4().hex
            connection.execute(
                "INSERT INTO billing_ledger(id,user_id,request_id,entry_type,feature,units,paid_units,metadata,created_at) VALUES (?, ?, ?, 'grant', ?, ?, ?, ?, ?)",
                (ledger_id, user_id, request_id, source, units, units, metadata, now),
            )
            connection.commit()
            return {
                "ledger_id": ledger_id,
                "units": units,
                "usage": self._usage_in_transaction(connection, user_id, now),
            }

    def create_order(
        self,
        user_id: str,
        plan_id: str,
        *,
        provider: str = "unconfigured",
        request_id: str | None = None,
    ) -> dict:
        if not user_id or provider not in {"unconfigured", "wechat", "alipay"}:
            raise BillingError("订单参数无效")
        if request_id is not None and (not request_id or len(request_id) > 128):
            raise BillingError("订单请求标识无效")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if request_id:
                previous = connection.execute(
                    "SELECT o.* FROM billing_orders o JOIN billing_order_requests r ON r.order_id=o.id WHERE r.user_id=? AND r.request_id=?",
                    (user_id, request_id),
                ).fetchone()
                if previous:
                    if (
                        previous["plan_id"] != plan_id
                        or previous["provider"] != provider
                    ):
                        raise BillingConflict("订单请求标识已用于其他套餐或支付方式")
                    return dict(previous)
            row = connection.execute(
                "SELECT id, price_cents, credits FROM billing_plans WHERE id=? AND active=1 AND price_cents>0",
                (plan_id,),
            ).fetchone()
            plan = dict(row) if row else None
            if not plan:
                raise BillingError("套餐不存在或无需购买")
            order_id = uuid4().hex
            now = int(time())
            connection.execute(
                "INSERT INTO billing_orders(id,user_id,plan_id,amount_cents,credits,provider,status,created_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
                (
                    order_id,
                    user_id,
                    plan_id,
                    plan["price_cents"],
                    plan["credits"],
                    provider,
                    now,
                ),
            )
            if request_id:
                connection.execute(
                    "INSERT INTO billing_order_requests VALUES (?, ?, ?)",
                    (user_id, request_id, order_id),
                )
            connection.commit()
        return self.order(user_id, order_id)

    def order(self, user_id: str, order_id: str) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM billing_orders WHERE id=? AND user_id=?",
                (order_id, user_id),
            ).fetchone()
        if not row:
            raise BillingError("订单不存在")
        return dict(row)

    def settle_verified_order(
        self,
        order_id: str,
        *,
        provider: str,
        transaction_id: str,
        amount_cents: int,
        currency: str = "CNY",
    ) -> dict:
        """Internal boundary: invoke only after authenticating the provider event.

        Order transition and credit grant commit in the SAME transaction. A
        browser success URL or a checkout response must never call this method.
        """
        if (
            provider not in {"wechat", "alipay"}
            or not transaction_id
            or len(transaction_id) > 128
        ):
            raise BillingError("支付流水无效")
        if type(amount_cents) is not int or amount_cents <= 0 or currency != "CNY":
            raise BillingError("支付金额或币种无效")
        payment_id = f"{provider}:{transaction_id}"
        now = int(time())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM billing_orders WHERE id=?", (order_id,)
            ).fetchone()
            if (
                not row
                or row["provider"] != provider
                or row["amount_cents"] != amount_cents
            ):
                raise BillingError("支付通知与订单不匹配")
            if row["status"] == "paid":
                if row["provider_order_id"] != payment_id:
                    raise BillingConflict("订单已由其他支付流水完成")
                return dict(row)
            if row["status"] != "pending":
                raise BillingConflict("订单状态不支持入账")
            if connection.execute(
                "SELECT 1 FROM billing_orders WHERE provider_order_id=?", (payment_id,)
            ).fetchone():
                raise BillingConflict("支付流水已用于其他订单")
            self._ensure_account(connection, row["user_id"], now)
            connection.execute(
                "UPDATE billing_accounts SET paid_credits=paid_credits+?, updated_at=? WHERE user_id=?",
                (row["credits"], now, row["user_id"]),
            )
            connection.execute(
                "INSERT INTO billing_ledger(id,user_id,request_id,entry_type,feature,units,paid_units,metadata,created_at) VALUES(?,?,?,'grant','payment',?,?,?,?)",
                (
                    uuid4().hex,
                    row["user_id"],
                    f"payment:{order_id}",
                    row["credits"],
                    row["credits"],
                    _json(
                        {
                            "order_id": order_id,
                            "provider": provider,
                            "transaction_id": transaction_id,
                            "amount_cents": amount_cents,
                            "currency": currency,
                        }
                    ),
                    now,
                ),
            )
            connection.execute(
                "UPDATE billing_orders SET status='paid',provider_order_id=?,paid_at=? WHERE id=?",
                (payment_id, now, order_id),
            )
            connection.commit()
        return self.order(row["user_id"], order_id)

    def audit(self) -> dict:
        """Reconcile purchased credits against the append-only ledger."""
        with self._connection() as connection:
            mismatches = connection.execute("""
                SELECT a.user_id, a.paid_credits,
                       COALESCE(SUM(CASE WHEN l.entry_type='consume' THEN -l.paid_units ELSE l.paid_units END),0) AS expected
                FROM billing_accounts a LEFT JOIN billing_ledger l ON l.user_id=a.user_id
                GROUP BY a.user_id HAVING a.paid_credits != expected
            """).fetchall()
            orders = connection.execute(
                "SELECT o.id FROM billing_orders o LEFT JOIN billing_ledger l ON l.request_id='payment:' || o.id WHERE o.status='paid' AND (l.id IS NULL OR l.user_id!=o.user_id OR l.paid_units!=o.credits)"
            ).fetchall()
        return {
            "ok": not mismatches and not orders,
            "accounts": [dict(row) for row in mismatches],
            "orders": [row[0] for row in orders],
        }


def _json(value: dict | None) -> str:
    import json

    return json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"))
