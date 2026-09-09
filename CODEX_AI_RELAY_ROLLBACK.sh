#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
backup=${1:-"$root/.install/codex-ai-relay-ai_config.json.original"}
target=${2:-"$root/Volume/ai_config.json"}

test -f "$backup"
mkdir -p "$(dirname -- "$target")"
cp -- "$backup" "$target"
printf '%s\n' "Restored AI relay configuration: previous Base URL, protocol, models, and API key are active"
