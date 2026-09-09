#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
patch_file="$root/ARCHIVE_DOWNLOAD.diff"

git -C "$root" apply -R --check "$patch_file"
git -C "$root" apply -R "$patch_file"
printf '%s\n' "Restored archive download behavior: removed the CSRF header forwarding and delayed Blob URL cleanup"
