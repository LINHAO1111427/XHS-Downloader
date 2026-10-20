"""Offline initialization, accounting reconciliation and consistent backups."""

import argparse
import getpass
import json
from pathlib import Path

from auth import AuthStore
from billing import BillingStore


from storage_backup import backup, restore, verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init-admin", "audit", "backup", "verify", "restore"])
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    root = args.data_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.command == "init-admin":
        from server_app import ServerLock

        with ServerLock(root / "server.lock"):
            auth = AuthStore(root / "users.db")
            if not auth.status()["needs_setup"]:
                parser.error("管理员已经初始化")
            email = input("管理员邮箱: ").strip()
            password = getpass.getpass("管理员密码（至少10位，含字母数字）: ")
            if password != getpass.getpass("再次输入密码: "):
                parser.error("两次密码不同")
            user = auth.register(email, "超级管理员", password)
            auth.set_registration_enabled(False)
        print(
            json.dumps(
                {"id": user["id"], "role": user["role"], "registration_enabled": False},
                ensure_ascii=False,
            )
        )
    elif args.command == "audit":
        result = BillingStore(root / "billing.db").audit()
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(0 if result["ok"] else 1)
    elif args.command == "verify":
        print(json.dumps(verify(root)))
    elif args.command == "restore":
        if args.destination is None:
            parser.error("restore 需要 --destination（新目录）")
        print(json.dumps(restore(root, args.destination)))
    else:
        if args.destination is None:
            parser.error("backup 需要 --destination")
        print(backup(root, args.destination))


if __name__ == "__main__":
    main()
