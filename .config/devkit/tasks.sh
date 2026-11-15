#!/bin/sh
# Managed by devkit (github.com/hiqdev/devkit): release tasks, .config/mise/conf.d/devkit.toml runs them.
set -eu
cd "$(dirname "$0")/../.."
INIT=src/uwiki/__init__.py

die() { echo "$*" >&2; exit 1; }

version() {
    v=$(sed -n 's/^__version__ = "\([0-9]*\.[0-9]*\.[0-9]*\)"$/\1/p' "$INIT")
    [ -n "$v" ] || die "no __version__ = \"X.Y.Z\" in $INIT"
    echo "$v"
}

# tests, bumps the version: patch, minor or major; commits and tags it
bump() {
    [ -z "$(git status --porcelain)" ] || die 'commit or stash changes first'
    v=$(version) || exit
    v=$(echo "$v" | awk -F. -v part="$1" '{
        if (part == "major") print $1+1 ".0.0"
        else if (part == "minor") print $1 "." $2+1 ".0"
        else print $1 "." $2 "." $3+1 }')
    mise run test
    sed "s/^__version__ = \".*\"$/__version__ = \"$v\"/" "$INIT" > "$INIT.new" && mv "$INIT.new" "$INIT"
    git commit -q -m "v$v" "$INIT"
    git tag "v$v"
    echo "tagged v$v, mise run release to publish"
}

# pushes master and the tag at once, CI publishes the release
release() {
    v=$(version) || exit
    git tag --points-at HEAD | grep -qx "v$v" || die "HEAD is not tagged v$v, mise run patch first"
    git push --atomic origin master "v$v"
}

# installs the tagged version with mise, it becomes latest locally without GitHub API lag
up() {
    v=$(version) || exit
    mise install "pipx:hiqsol/uwiki@v$v"
    mise prune --yes pipx:hiqsol/uwiki
    # the uwiki a shell outside this project gets, not one this project's mise config puts first
    got=$("$(cd && mise which uwiki)" --version)
    [ "$got" = "uwiki $v" ] || die "$got on PATH, not $v"
    echo "$got"
}

# removes build output and __pycache__ folders, those of .venv and other dot folders left alone
clean() {
    rm -rf dist build
    find . -path './.*' -prune -o -name __pycache__ -type d -prune -exec rm -rf {} +
}

case "${1:-}" in
    version | release | up | clean) "$1" ;;
    bump) case "${2:-}" in patch | minor | major) bump "$2" ;; *) die 'usage: tasks.sh bump patch|minor|major' ;; esac ;;
    *) die 'usage: tasks.sh version|bump PART|release|up|clean' ;;
esac
