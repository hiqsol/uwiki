<p align="center"><img src="docs/logo/uwiki.svg" alt="uWiki" height="72"></p>

# uWiki - micro wiki

[![test](https://github.com/hiqsol/uwiki/actions/workflows/test.yml/badge.svg)](https://github.com/hiqsol/uwiki/actions/workflows/test.yml)

Markdown utility for Obsidian vaults and plain markdown docs: builds a vault into one HTML or markdown file,
serves it rebuilding on change, checks it, counts it, links mentions and record ids as `P:24` or `HQD-640`,
rewraps lines, moves pages rewriting links, and is a language server for editors.

## Installation

Python 3.11 or later, with [mise](https://mise.jdx.dev) or [uv](https://docs.astral.sh/uv/):

```
mise use -g pipx:hiqsol/uwiki
uv tool install git+https://github.com/hiqsol/uwiki
```

## Usage

```
uwiki build docs             # docs.html and docs.md, one file each
uwiki serve docs --open      # serve the HTML, rebuilding and reloading on change
uwiki check docs --orphans   # broken links, front matter, unlinked pages
uwiki mv docs/A.md docs/B.md # move a page rewriting every link to it
```

`uwiki <command> --help` lists all options, [docs](docs/README.md) tell everything:
[concepts](docs/Concepts.md), [commands](docs/Commands.md), [config](docs/Config.md),
[HTML page](docs/HTML-page.md), [editors](docs/Editors.md), [development](docs/Development.md).

## License

MIT, see [LICENSE](LICENSE).
