from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from secrets import token_bytes, token_urlsafe
from threading import Lock
from time import monotonic, time
from typing import Iterator
from uuid import uuid4


SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


class AuthError(ValueError):
    pass


class RegistrationClosed(AuthError):
    pass


class AccountConflict(AuthError):
    pass


class InvalidCredentials(AuthError):
    pass


class AccountDisabled(AuthError):
    pass


class AdminActionError(AuthError):
    pass


class LoginBlocked(AuthError):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"登录尝试过多，请在 {retry_after} 秒后重试")
        self.retry_after = retry_after


def normalize_email(value: str) -> str:
    email = value.strip().casefold()
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        raise AuthError("请输入有效的邮箱地址")
    return email


def validate_display_name(value: str) -> str:
    display_name = " ".join(value.strip().split())
    if not 2 <= len(display_name) <= 40:
        raise AuthError("昵称长度需要在 2 到 40 个字符之间")
    return display_name


def validate_password(value: str) -> str:
    if not PASSWORD_MIN_LENGTH <= len(value) <= PASSWORD_MAX_LENGTH:
        raise AuthError("密码长度需要在 10 到 128 个字符之间")
    if not any(character.isalpha() for character in value) or not any(
        character.isdigit() for character in value
    ):
        raise AuthError("密码必须同时包含字母和数字")
    return value


def hash_password(password: str) -> str:
    salt = token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=32,
    )
    return "$".join(
        (
            "scrypt",
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_value, digest_value = encoded.split("$")
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_value.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_value.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


class LoginThrottle:
    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 15 * 60,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = {}
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = monotonic()
        with self._lock:
            attempts = self._recent(key, now)
            if len(attempts) >= self.max_attempts:
                retry_after = max(1, int(self.window_seconds - (now - attempts[0])))
                raise LoginBlocked(retry_after)

    def fail(self, key: str) -> None:
        now = monotonic()
        with self._lock:
            attempts = self._recent(key, now)
            attempts.append(now)
            self._attempts[key] = attempts

    def success(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def _recent(self, key: str, now: float) -> list[float]:
        threshold = now - self.window_seconds
        attempts = [value for value in self._attempts.get(key, []) if value > threshold]
        if attempts:
            self._attempts[key] = attempts
        else:
            self._attempts.pop(key, None)
        return attempts


class AuthStore:
    def __init__(self, path: Path, session_ttl: int = SESSION_TTL_SECONDS) -> None:
        self.path = path
        self.session_ttl = session_ttl
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._dummy_password = hash_password("timing-equalizer-2026")

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
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    last_login_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    csrf_token TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sessions_user_id ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS sessions_expires_at ON sessions(expires_at);
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT OR IGNORE INTO app_settings(key, value)
                VALUES ('registration_enabled', 'true');
                """
            )
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def status(self) -> dict:
        with self._connection() as connection:
            user_count = int(
                connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            )
            enabled = self._registration_enabled(connection)
        return {
            "needs_setup": user_count == 0,
            "registration_enabled": user_count == 0 or enabled,
        }

    def register(self, email: str, display_name: str, password: str) -> dict:
        normalized_email = normalize_email(email)
        normalized_name = validate_display_name(display_name)
        password_hash = hash_password(validate_password(password))
        now = int(time())
        user_id = uuid4().hex
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            user_count = int(
                connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            )
            if user_count and not self._registration_enabled(connection):
                connection.rollback()
                raise RegistrationClosed("管理员已关闭新用户注册")
            role = "admin" if user_count == 0 else "user"
            try:
                connection.execute(
                    """
                    INSERT INTO users(
                        id, email, display_name, password_hash, role,
                        is_active, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        user_id,
                        normalized_email,
                        normalized_name,
                        password_hash,
                        role,
                        now,
                        now,
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as error:
                connection.rollback()
                raise AccountConflict("该邮箱已经注册") from error
        return self.get_user(user_id)

    def authenticate(self, email: str, password: str) -> dict:
        try:
            normalized_email = normalize_email(email)
        except AuthError as error:
            verify_password(password, self._dummy_password)
            raise InvalidCredentials("邮箱或密码错误") from error
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email = ?",
                (normalized_email,),
            ).fetchone()
            encoded = row["password_hash"] if row else self._dummy_password
            valid = verify_password(password, encoded)
            if not row or not valid:
                raise InvalidCredentials("邮箱或密码错误")
            if not row["is_active"]:
                raise AccountDisabled("账号已被停用")
            now = int(time())
            connection.execute(
                "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
                (now, now, row["id"]),
            )
            connection.commit()
        return self.get_user(str(row["id"]))

    def create_session(self, user_id: str) -> dict:
        token = token_urlsafe(32)
        csrf_token = token_urlsafe(24)
        now = int(time())
        expires_at = now + self.session_ttl
        with self._connection() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            connection.execute(
                """
                INSERT INTO sessions(
                    token_hash, user_id, csrf_token, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (self._token_hash(token), user_id, csrf_token, now, expires_at),
            )
            connection.commit()
        return {
            "token": token,
            "csrf_token": csrf_token,
            "expires_at": expires_at,
        }

    def session(self, token: str) -> dict | None:
        if not token:
            return None
        now = int(time())
        token_hash = self._token_hash(token)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT
                    sessions.csrf_token,
                    sessions.expires_at,
                    users.id,
                    users.email,
                    users.display_name,
                    users.role,
                    users.is_active,
                    users.created_at,
                    users.updated_at,
                    users.last_login_at
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
            if not row or not row["is_active"]:
                connection.execute(
                    "DELETE FROM sessions WHERE token_hash = ?",
                    (token_hash,),
                )
                connection.commit()
                return None
        return {
            "csrf_token": str(row["csrf_token"]),
            "expires_at": int(row["expires_at"]),
            "user": self._public_user(row),
        }

    def delete_session(self, token: str) -> None:
        if not token:
            return
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?",
                (self._token_hash(token),),
            )
            connection.commit()

    def get_user(self, user_id: str) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            raise AuthError("用户不存在")
        return self._public_user(row)

    def update_profile(self, user_id: str, display_name: str) -> dict:
        normalized_name = validate_display_name(display_name)
        with self._connection() as connection:
            connection.execute(
                "UPDATE users SET display_name = ?, updated_at = ? WHERE id = ?",
                (normalized_name, int(time()), user_id),
            )
            connection.commit()
        return self.get_user(user_id)

    def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> None:
        validate_password(new_password)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT password_hash FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if not row or not verify_password(current_password, row["password_hash"]):
                raise InvalidCredentials("当前密码错误")
            connection.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (hash_password(new_password), int(time()), user_id),
            )
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            connection.commit()

    def list_users(self) -> list[dict]:
        now = int(time())
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT users.*, COUNT(sessions.token_hash) AS session_count
                FROM users
                LEFT JOIN sessions
                    ON sessions.user_id = users.id AND sessions.expires_at > ?
                GROUP BY users.id
                ORDER BY users.created_at ASC
                """,
                (now,),
            ).fetchall()
        return [
            {**self._public_user(row), "session_count": int(row["session_count"])}
            for row in rows
        ]

    def set_user_active(
        self,
        user_id: str,
        is_active: bool,
        acting_user_id: str,
    ) -> dict:
        if user_id == acting_user_id and not is_active:
            raise AdminActionError("不能停用当前登录账号")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT role, is_active FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                connection.rollback()
                raise AuthError("用户不存在")
            if row["role"] == "admin" and row["is_active"] and not is_active:
                admin_count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1"
                    ).fetchone()[0]
                )
                if admin_count <= 1:
                    connection.rollback()
                    raise AdminActionError("必须保留至少一个启用的管理员")
            connection.execute(
                "UPDATE users SET is_active = ?, updated_at = ? WHERE id = ?",
                (int(is_active), int(time()), user_id),
            )
            if not is_active:
                connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            connection.commit()
        return self.get_user(user_id)

    def registration_enabled(self) -> bool:
        with self._connection() as connection:
            return self._registration_enabled(connection)

    def set_registration_enabled(self, enabled: bool) -> bool:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO app_settings(key, value) VALUES ('registration_enabled', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                ("true" if enabled else "false",),
            )
            connection.commit()
        return enabled

    @staticmethod
    def _registration_enabled(connection: sqlite3.Connection) -> bool:
        row = connection.execute(
            "SELECT value FROM app_settings WHERE key = 'registration_enabled'"
        ).fetchone()
        return not row or str(row["value"]).lower() == "true"

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _public_user(row: sqlite3.Row) -> dict:
        return {
            "id": str(row["id"]),
            "email": str(row["email"]),
            "display_name": str(row["display_name"]),
            "role": str(row["role"]),
            "is_active": bool(row["is_active"]),
            "created_at": int(row["created_at"]),
            "updated_at": int(row["updated_at"]),
            "last_login_at": (
                int(row["last_login_at"]) if row["last_login_at"] else None
            ),
        }
