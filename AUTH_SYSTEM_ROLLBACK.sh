#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
target=${1:-$root}
patch_file="$root/AUTH_SYSTEM.diff"

git -C "$target" apply --reverse --check "$patch_file"
git -C "$target" apply --reverse "$patch_file"

config="$target/Volume/ai_config.json"
if [ -f "$config" ]; then
    if [ -x "$target/.venv/Scripts/python.exe" ]; then
        python="$target/.venv/Scripts/python.exe"
    elif command -v python >/dev/null 2>&1; then
        python=python
    else
        python=python3
    fi
    "$python" - "$config" <<'PY'
import json
import os
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

path = Path(sys.argv[1])
with path.open("r", encoding="utf-8") as source:
    config = json.load(source)
config["base_url"] = "http://127.0.0.1:8088/v1"
with NamedTemporaryFile(
    "w",
    encoding="utf-8",
    dir=path.parent,
    prefix=f".{path.stem}.",
    suffix=".tmp",
    delete=False,
) as temporary:
    json.dump(config, temporary, ensure_ascii=False, indent=2)
    temporary.write("\n")
    temporary_path = Path(temporary.name)
temporary_path.replace(path)
try:
    os.chmod(path, 0o600)
except OSError:
    pass
PY
fi

printf '%s\n' "Restored pre-account web workspace and local relay URL"
