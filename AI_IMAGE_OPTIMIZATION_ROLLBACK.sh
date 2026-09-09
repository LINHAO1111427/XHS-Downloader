#!/usr/bin/env sh
set -eu

root=${1:-"$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"}
backup_dir="$root/.install/ai-image-optimize-original"

test -f "$backup_dir/web_app.py"
test -f "$backup_dir/test_web_app.py"
test -f "$root/web_app.py"
test -f "$root/tests/test_web_app.py"

cp -- "$backup_dir/web_app.py" "$root/web_app.py"
cp -- "$backup_dir/test_web_app.py" "$root/tests/test_web_app.py"
printf '%s\n' "Restored AI image handling: images larger than 8 MB are rejected before relay submission"
