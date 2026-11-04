.PHONY: test build clean version patch minor major release up

INIT = src/uwiki/__init__.py
VERSION = $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' $(INIT))

test:
	uv run --no-project --with markdown-it-py python -m unittest discover tests
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

# install current tag with mise, it becomes `latest` locally without GitHub API or versions host lag
up:
	mise install pipx:hiqsol/uwiki@v$(VERSION)
	mise prune --yes pipx:hiqsol/uwiki
	@uwiki --version | grep -qx 'uwiki $(VERSION)' || { echo "uwiki on PATH is not $(VERSION)" >&2; exit 1; }
	@uwiki --version
