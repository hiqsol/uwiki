#!/bin/sh
# Managed by devkit (github.com/hiqdev/devkit): `devkit update` rewrites it, change the template instead.
#MISE description="push $DEVKIT_BRANCH and the version's tag at once, CI publishes the release"
#MISE hide=true
set -eu
v=$("$(dirname "$0")/version.sh")
git tag --points-at HEAD | grep -qx "v$v" || { echo "HEAD is not tagged v$v, mise run patch first" >&2; exit 1; }
git push --atomic origin "${DEVKIT_BRANCH:?devkit.toml sets it}" "v$v"
