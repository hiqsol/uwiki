# uWiki -  micro wiki

Markdown utility for wikis: builds folder of markdown files into single HTML or markdown file,
checks it, counts statistics and rewraps long lines.
Links resolve the same way in every command. I use it for Obsidian vaults.

## Installation

With [mise](https://mise.jdx.dev):

```
mise use -g pipx:hiqsol/uwiki
```

Or with [uv](https://docs.astral.sh/uv/):

```
uv tool install git+https://github.com/hiqsol/uwiki
```

## Usage

```
uwiki build <folder> [title] [--html] [--md] [-o <output-dir>]
uwiki check <folder|file>...
uwiki stats <folder|file>... [--by folder|<frontmatter key>] [--top N] [--json]
uwiki wrap [-w 70] [--check] <file>...
```

`build` writes `<title>.html` and `<title>.md` (title defaults to folder name),
`--html` or `--md` to write only one of them.

`check` reports unresolved wiki links and headings, missing images,
frontmatter syntax and list numbering as `path:line: message`, exits 1 if any.

`stats` counts pages, words, lines, headings, list items, wiki and external links and images
outside code, grouped by folder or frontmatter key, e.g. `--by status`.
It lists the largest pages and orphans: pages not linked from the counted ones, folder pages excepted.

`wrap` rewraps paragraphs and list items with lines longer than width (tab counts as 4),
leaving frontmatter, code, tables and headings as is, never splitting wiki links and inline code.
`--check` reports such lines instead and exits 1 if any.

Supported Obsidian syntax:

- `[[Page]]`, `[[Page|text]]`, `[[folder/Page]]`, `[[Page#Heading]]`, `[[#Heading]]`
- `![[Page]]`, `![[Page#Heading]]` embeds, `![[image.png]]`, `![[image.png|300]]`
- callouts `> [!note] Title`, foldable `> [!note]-`
- YAML front matter is stripped

Folder page is `index.md` or file named as folder, e.g. `Projects/Project.md`.

The HTML page is self-contained, light or dark by system preference:

- sidebar with collapsible contents following the page being read
- fuzzy full text search: press `/` or `Ctrl+K`, tolerates typos and abbreviations,
  `↑` `↓` `Enter` to open a result with matched words highlighted in text, `Esc` to clear

## Library

Project specific checks can build on uwiki, e.g. a script run by `uv run --script`:

```python
# /// script
# dependencies = ["uwiki @ git+https://github.com/hiqsol/uwiki@v0.2.0"]
# ///
import uwiki

problems = uwiki.check(['docs'])         # same lines as `uwiki check docs`
data = uwiki.stats(['docs'], by='status')  # same data as `uwiki stats --json`
```

## Tests

```
python3 -m unittest discover tests
```

## Release

Bump `version` in `pyproject.toml`, commit, tag `v<version>` and push the tag:
the release workflow runs tests and creates GitHub release, `mise up` picks it up.
