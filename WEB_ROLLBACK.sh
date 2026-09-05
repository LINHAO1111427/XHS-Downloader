#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

for file in \
    web_app.py \
    start-web.ps1 \
    stop-web.ps1 \
    tests/test_web_app.py \
    static/web/index.html \
    static/web/styles.css \
    static/web/app.js \
    static/web/lucide.min.js \
    static/web/logo.png \
    WEB_APP.diff \
    WEB_VERIFICATION.txt
do
    rm -f -- "$root/$file"
done

rm -f -- "$root/../Start-XHS-Web.cmd" "$root/../Stop-XHS-Web.cmd"
rmdir "$root/static/web" 2>/dev/null || true
printf '%s\n' "Restored pre-web behavior: web runtime, page assets, tests, and launchers removed; rollback record retained"
