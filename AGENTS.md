# uwiki

## Tests

- `mise run test` runs the suite via uv with the `markdown-it-py`, `linkify-it-py` and `watchfiles` packages; tests require them and never skip
- `mise run lint` checks pages (uwiki check, markdownlint, typos, Vale) and the repo (hygiene, gitleaks), see `hk.pkl`;
  `devkit doctor` says what keeps it or the pre-commit hook from running; lint, hooks and the files devkit owns:
  `.config/devkit/AGENTS.md`

## Release

A change is not done until it is released: users install via mise, which only sees tagged GitHub releases.

After merging user-facing changes into `master`, ask whether to release, then:

1. `mise run patch` (fixes) or `mise run minor` (features) — tests, bumps `src/uwiki/__init__.py`, commits, tags
2. `mise run release` — pushes `master` and the tag atomically; the release workflow tests and creates the GitHub release
3. `mise run up` — installs the new tag locally via mise and verifies `uwiki --version`

Never push a `v*` tag without the user's go-ahead: the tag push publishes the release.
