"""Migrate the personal daily collector to knowledge-based selection in-place.

Run inside the active container: python /path/to/enable_daily_selection.py --data-root /data
Only the daily-plan and legacy-schedule fields change; snapshots and sessions stay intact.
"""
import argparse
import json
from pathlib import Path
import sqlite3

from daily_selection import DailySelectionConfig
from market_discovery import DiscoverySettings
from viral_notes import ViralStore


def enable(root):
    settings = DiscoverySettings(root / "discovery-settings.json")
    old = settings.read()
    store = ViralStore(root / "viral_notes.db")
    legacy = store.config()
    with sqlite3.connect(f"file:{(root / 'users.db').as_posix()}?mode=ro", uri=True) as db:
        owners = db.execute("SELECT id FROM users WHERE role='admin' AND is_active=1 ORDER BY created_at LIMIT 1").fetchall()
    if not owners:
        raise RuntimeError("每日选品需要已有管理员账号")
    backup = root / ".maintenance/daily-selection-20260929/config-before.json"
    if not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(json.dumps({"viral": legacy,
            "daily_selection": old.get("daily_selection"), "daily_selection_pause": old.get("daily_selection_pause"),
            "mcp_binary": old.get("mcp_binary")}, ensure_ascii=False, indent=2), encoding="utf-8")
    prior = old.get("daily_selection")
    if prior:
        config = DailySelectionConfig.model_validate({k: v for k, v in prior.items() if k != "owner_id"})
        owner = prior["owner_id"]
    else:
        config = DailySelectionConfig(enabled=True, at=legacy.get("at", "09:00"),
            keywords=(legacy.get("rules", {}).get("keywords") or ["潮玩", "家居", "女生精致小物"])[:6],
            min_interactions=legacy.get("rules", {}).get("min_interactions", 500))
        owner = owners[0][0]
    config.enabled = True
    settings.update(daily_selection=config.model_dump() | {"owner_id": owner})
    patched = root / "tools/xhs-mcp/xiaohongshu-mcp-linux-amd64-domready"
    if patched.is_file():
        settings.update(mcp_binary=patched.relative_to(root).as_posix())
    legacy["enabled"] = False
    # The disabled legacy screen shows the same recent/strict follower convention.
    legacy["rules"].update(hours=168, time_range="rolling", max_followers=999)
    store.save_config(legacy)
    print(json.dumps({"enabled": True, "at": config.at, "timezone": "Asia/Shanghai", "keywords": config.keywords,
        "legacy_schedule_enabled": False, "backup": str(backup)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    enable(parser.parse_args().data_root.resolve())
