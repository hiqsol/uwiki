#!/bin/sh
# Managed by devkit (github.com/hiqdev/devkit): `devkit update` rewrites it, change the template instead.
#MISE description="install the tagged version with mise, it becomes latest locally without GitHub API lag"
#MISE hide=true
set -eu
pkg=${DEVKIT_PACKAGE:?devkit.toml sets it}
cmd=${DEVKIT_COMMAND:?devkit.toml sets it}
v=$("$(dirname "$0")/version.sh")
mise install "$pkg@v$v"
mise prune --yes "$pkg"
# the command a shell outside this project gets, not one this project's mise config puts first
got=$("$(cd && mise which "$cmd")" --version)
[ "$got" = "$cmd $v" ] || { echo "$got on PATH, not $v" >&2; exit 1; }
echo "$got"
