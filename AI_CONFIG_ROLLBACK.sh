#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_ROOT="${1:-$SCRIPT_DIR}"
TARGET_ROOT="$(cd "$TARGET_ROOT" && pwd)"
BASELINE="$SCRIPT_DIR/.install/ai-config-baseline"

test -f "$BASELINE/web_app.py"
mkdir -p "$TARGET_ROOT/static/web" "$TARGET_ROOT/tests"

cp "$BASELINE/web_app.py" "$TARGET_ROOT/web_app.py"
cp "$BASELINE/static/web/index.html" "$TARGET_ROOT/static/web/index.html"
cp "$BASELINE/static/web/app.js" "$TARGET_ROOT/static/web/app.js"
cp "$BASELINE/static/web/styles.css" "$TARGET_ROOT/static/web/styles.css"
cp "$BASELINE/tests/test_web_app.py" "$TARGET_ROOT/tests/test_web_app.py"
rm -f "$TARGET_ROOT/ai_gateway.py"

printf 'Restored branch field: ai_gateway=absent; enhancement=lanczos_2x\n'
printf 'Restored pre-AI-config files at: %s\n' "$TARGET_ROOT"
