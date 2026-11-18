#!/bin/sh
# Managed by devkit (github.com/hiqdev/devkit): `devkit update` rewrites it, change the template instead.
#MISE description="the version in $DEVKIT_VERSION_FILE: __version__ = \"X.Y.Z\""
#MISE hide=true
set -eu
f=${DEVKIT_VERSION_FILE:?devkit.toml sets it}
v=$(sed -n 's/^__version__ = "\([0-9]*\.[0-9]*\.[0-9]*\)"$/\1/p' "$f")
[ -n "$v" ] || { echo "no __version__ = \"X.Y.Z\" in $f" >&2; exit 1; }
echo "$v"
