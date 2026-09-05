#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cp "$root/.install/settings.baseline.json" "$root/Volume/settings.json"
printf '%s\n' "Restored baseline settings: image_format=JPEG, live_download=false, folder_mode=false, write_mtime=false, note_format=empty"
