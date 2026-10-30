.PHONY: test build clean version patch minor major release up

INIT = src/uwiki/__init__.py
VERSION = $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' $(INIT))
# mise reads releases from GitHub directly, its versions host and cache lag new releases
MISE_FRESH = MISE_USE_VERSIONS_HOST=false MISE_FETCH_REMOTE_VERSIONS_CACHE=0s

test:
	python3 -m unittest discover tests
build:
	uv build
clean:
	rm -rf dist build
	find . -name __pycache__ -prune -exec rm -rf {} +
version:
	@echo $(VERSION)

# bump version in $(INIT), commit and tag it, e.g. 0.2.1 -> make minor -> 0.3.0
patch minor major:
	@test -z "$$(git status --porcelain)" || { echo 'commit or stash changes first' >&2; exit 1; }
	@$(MAKE) --no-print-directory test
	@v=$$(echo $(VERSION) | awk -F. -v part=$@ '{ \
		if (part == "major") print $$1+1 ".0.0"; \
		else if (part == "minor") print $$1 "." $$2+1 ".0"; \
		else print $$1 "." $$2 "." $$3+1 }'); \
	sed -i "s/^__version__ = \".*\"/__version__ = \"$$v\"/" $(INIT) && \
	git commit -q -m "v$$v" $(INIT) && git tag "v$$v" && \
	echo "tagged v$$v, make release to publish"

# push branch and tag, the release workflow tests and creates GitHub release
release:
	@test "$$(git tag --points-at HEAD)" = "v$(VERSION)" || { echo 'HEAD is not tagged v$(VERSION), make patch first' >&2; exit 1; }
	git push --atomic origin master v$(VERSION)

# wait for GitHub release of current version, then upgrade the mise installed uwiki
up:
	@for i in $$(seq 30); do \
		curl -fsS -o /dev/null https://api.github.com/repos/hiqsol/uwiki/releases/tags/v$(VERSION) 2>/dev/null && break; \
		[ $$i = 30 ] && { echo 'no release v$(VERSION) yet, see GitHub Actions' >&2; exit 1; }; \
		sleep 10; \
	done
	$(MISE_FRESH) mise up pipx:hiqsol/uwiki
	uwiki --help >/dev/null
