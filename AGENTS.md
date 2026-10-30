# uwiki

## Tests

- `make test` runs the suite via uv with the `markdown` package; tests require it and never skip

## Release

A change is not done until it is released: users install via mise, which only sees tagged GitHub releases.

After merging user-facing changes into `master`, ask whether to release, then:

1. `make patch` (fixes) or `make minor` (features) — tests, bumps `src/uwiki/__init__.py`, commits, tags
2. `make release` — pushes `master` and the tag atomically; the release workflow tests and creates the GitHub release
3. `make up` — installs the new tag locally via mise and verifies `uwiki --version`

Never push a `v*` tag without the user's go-ahead: the tag push publishes the release.
