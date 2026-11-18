#!/bin/sh
# Managed by devkit (github.com/hiqdev/devkit): `devkit update` rewrites it, change the template instead.
#MISE description="push $DEVKIT_BRANCH and the version's tag at once, CI publishes the release"
#MISE hide=true
set -eu
v=$("$(dirname "$0")/version.sh")
die() { echo "$*" >&2; exit 1; }
if ! git tag --points-at HEAD | grep -qx "v$v"; then
    git rev-parse -q --verify "refs/tags/v$v" >/dev/null &&
        die "v$v tags another commit, not HEAD: mise run patch (or minor, major) for a new version"
    die "HEAD is not tagged v$v: mise run patch (or minor, major) bumps and tags it; a version set by hand: git tag v$v"
fi
git push --atomic origin "${DEVKIT_BRANCH:?devkit.toml sets it}" "v$v"
