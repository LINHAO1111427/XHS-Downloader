"""Prepare a portable Docker copy; never alter the original desktop directory."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from ai_gateway import AIConfigStore, AIGateway
from storage_backup import restore


def docker_url(value):
    parsed = urlsplit(value)
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return urlunsplit((parsed.scheme, "host.docker.internal" + (f":{parsed.port}" if parsed.port else ""), parsed.path, "", ""))
    return value


def prepare(snapshot: Path, destination: Path):
    gateway = AIGateway(AIConfigStore(snapshot / "ai_config.json"))
    config = gateway.store.runtime_config()
    text = gateway._text_relay_config()
    image = gateway._image_relay_config()
    result = restore(snapshot, destination)
    settings_path = destination / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8-sig"))
    settings["work_path"] = "/data"
    # Download paths in business tables are relative to this directory.
    settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    (destination / "Temp").mkdir(exist_ok=True)
    config.update(text)
    config.update(relay_source="portable", base_url=docker_url(text["base_url"]),
                  image_base_url=docker_url(image["base_url"]), image_api_key=image["api_key"])
    AIConfigStore(destination / "ai_config.json")._write(config)
    # A running dataset is no longer an immutable backup.
    (destination / "BACKUP.json").unlink()
    return {**result, "work_path": "/data", "relay_source": "portable", "image_relay_host": urlsplit(config["image_base_url"]).hostname}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.snapshot.resolve(), args.destination.resolve())))
