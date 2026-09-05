#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_ROOT="${1:-$SCRIPT_DIR}"
TARGET_ROOT="$(cd "$TARGET_ROOT" && pwd)"
BASELINE="$SCRIPT_DIR/.install/enhancement-baseline"

test -f "$BASELINE/web_app.py"
mkdir -p "$TARGET_ROOT/static/web" "$TARGET_ROOT/tests"

cp "$BASELINE/web_app.py" "$TARGET_ROOT/web_app.py"
cp "$BASELINE/pyproject.toml" "$TARGET_ROOT/pyproject.toml"
cp "$BASELINE/requirements.txt" "$TARGET_ROOT/requirements.txt"
cp "$BASELINE/uv.lock" "$TARGET_ROOT/uv.lock"
cp "$BASELINE/static/web/index.html" "$TARGET_ROOT/static/web/index.html"
cp "$BASELINE/static/web/app.js" "$TARGET_ROOT/static/web/app.js"
cp "$BASELINE/static/web/styles.css" "$TARGET_ROOT/static/web/styles.css"
cp "$BASELINE/tests/test_web_app.py" "$TARGET_ROOT/tests/test_web_app.py"
rm -f "$TARGET_ROOT/media_enhancer.py"

if [[ "$TARGET_ROOT" == "$SCRIPT_DIR" ]] && command -v uv >/dev/null 2>&1; then
    (cd "$TARGET_ROOT" && uv sync --frozen)
fi

printf 'Restored branch field: enhancements=absent; source_download=original\n'
printf 'Restored pre-enhancement files at: %s\n' "$TARGET_ROOT"
