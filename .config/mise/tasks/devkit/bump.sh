#!/bin/sh
# Managed by devkit (github.com/hiqdev/devkit): `devkit update` rewrites it, change the template instead.
#MISE description="check, bump the version: patch, minor or major; commit and tag it"
#MISE hide=true
set -eu
f=${DEVKIT_VERSION_FILE:?devkit.toml sets it}
die() { echo "$*" >&2; exit 1; }

part=${1:-}
case $part in patch | minor | major) ;; *) die 'usage: mise run devkit:bump patch|minor|major' ;; esac
[ -z "$(git status --porcelain)" ] || die 'commit or stash changes first'
v=$("$(dirname "$0")/version.sh")
v=$(echo "$v" | awk -F. -v part="$part" '{
    if (part == "major") print $1+1 ".0.0"
    else if (part == "minor") print $1 "." $2+1 ".0"
    else print $1 "." $2 "." $3+1 }')
mise run check
sed "s/^__version__ = \".*\"$/__version__ = \"$v\"/" "$f" > "$f.new" && mv "$f.new" "$f"
git commit -q -m "v$v" "$f"
git tag "v$v"
echo "tagged v$v, mise run release to publish"
