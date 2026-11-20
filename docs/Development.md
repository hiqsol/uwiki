# Development

[mise](https://mise.jdx.dev) pins the tools and runs the tasks, `mise tasks` lists them:
`mise.toml` has uwiki's own, [devkit](https://github.com/hiqdev/devkit) the lint and release ones,
in `.config/mise/conf.d/devkit.toml` and `.config/devkit/`; `devkit update` brings in devkit changes,
`devkit doctor` says what keeps lint or the hook from running.

```
mise run test                # run tests
mise run lint                # pages: uwiki check, markdownlint, typos, Vale; repo: hygiene, shellcheck, gitleaks
mise run fix                 # fix what markdownlint and the hygiene steps can; typos only reports
mise run links               # external links alive, lychee, on demand
mise run secrets             # gitleaks over the whole git history, on demand
mise run hooks               # git pre-commit hook: lint staged files
mise run patch|minor|major   # test, bump version, commit and tag it
mise run release             # push master and the tag, the release workflow publishes it
mise run up                  # install the tagged version with mise
```

## Tests

`mise run test` runs the end-to-end suite in `tests/` via uv with `markdown-it-py`, `linkify-it-py`
and `watchfiles`, the only dependencies; tests require them and never skip. CI runs it on Python 3.11 to 3.14.
The fixture vaults in `tests/fixtures` are left out of the build of this repo by `[tool.uwiki]` in `pyproject.toml`.

## Lint

[hk](https://hk.jdx.dev) runs devkit's steps, `hk.pkl` adds uwiki's settings. Page steps take the pages `uwiki ls` lists,
so uwiki.toml excludes hold for each: `uwiki check`, markdownlint by `.markdownlint.yaml`, typos,
Vale by `.vale.ini` with proselint and the vocabulary in `.vale/`; lychee for external links only, on demand,
a dead link being someone else's server.
Repo steps take every file but test fixtures: trailing whitespace, final newline, line endings, BOM, merge conflict markers,
names differing only in case, files over 500 kB, broken symlinks, shellcheck for shell scripts, and gitleaks for secrets.
The pre-commit hook checks staged files and rewrites nothing.

## Release

Users install via mise, which only sees tagged GitHub releases, so a change reaches them once released:

1. `mise run patch` (fixes) or `mise run minor` (features): tests, bumps `src/uwiki/__init__.py`, commits, tags
2. `mise run release`: pushes `master` and the tag atomically, the release workflow tests and creates the GitHub release
3. `mise run up`: installs the new tag locally via mise and verifies `uwiki --version`

[AGENTS.md](../AGENTS.md) has the same rules for agents.
