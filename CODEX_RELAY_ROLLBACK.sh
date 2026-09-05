#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_ROOT="${1:-$SCRIPT_DIR}"
TARGET_ROOT="$(cd "$TARGET_ROOT" && pwd)"
BASELINE="$SCRIPT_DIR/.install/codex-relay-baseline"

test -f "$BASELINE/ai_gateway.py"
mkdir -p "$TARGET_ROOT/static/web" "$TARGET_ROOT/tests"

cp "$BASELINE/ai_gateway.py" "$TARGET_ROOT/ai_gateway.py"
cp "$BASELINE/web_app.py" "$TARGET_ROOT/web_app.py"
cp "$BASELINE/static/web/index.html" "$TARGET_ROOT/static/web/index.html"
cp "$BASELINE/static/web/app.js" "$TARGET_ROOT/static/web/app.js"
cp "$BASELINE/static/web/styles.css" "$TARGET_ROOT/static/web/styles.css"
cp "$BASELINE/tests/test_web_app.py" "$TARGET_ROOT/tests/test_web_app.py"

if [[ -f "$TARGET_ROOT/Volume/ai_config.json" ]]; then
    mkdir -p "$TARGET_ROOT/.install"
    mv "$TARGET_ROOT/Volume/ai_config.json" \
        "$TARGET_ROOT/.install/ai_config.rollback.json"
fi

printf 'Restored branch field: ai_configured=false; protocol_field=absent\n'
printf 'Preserved previous AI config at: %s\n' \
    "$TARGET_ROOT/.install/ai_config.rollback.json"
