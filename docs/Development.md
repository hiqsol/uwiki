# Development

```
make test                    # run tests
make patch|minor|major       # test, bump version, commit and tag it
make release                 # push master and the tag, the release workflow publishes it
make up                      # install the tagged version with mise
```

## Tests

`make test` runs the end-to-end suite in `tests/` via uv with `markdown-it-py` and `linkify-it-py`,
the only dependencies; tests require them and never skip. CI runs it on Python 3.11 to 3.14.
The fixture vaults in `tests/fixtures` are left out of the build of this repo by `[tool.uwiki]` in `pyproject.toml`.

## Release

Users install via mise, which only sees tagged GitHub releases, so a change reaches them once released:

1. `make patch` (fixes) or `make minor` (features): tests, bumps `src/uwiki/__init__.py`, commits, tags
2. `make release`: pushes `master` and the tag atomically, the release workflow tests and creates the GitHub release
3. `make up`: installs the new tag locally via mise and verifies `uwiki --version`

[AGENTS.md](../AGENTS.md) has the same rules for agents.
