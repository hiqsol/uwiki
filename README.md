# uWiki - micro wiki

[![test](https://github.com/hiqsol/uwiki/actions/workflows/test.yml/badge.svg)](https://github.com/hiqsol/uwiki/actions/workflows/test.yml)

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
uwiki build <folder> [title] [--html] [--md] [-o <output-dir>] [--exclude GLOB] [--include GLOB]
uwiki check <folder|file>... [--exclude GLOB] [--include GLOB]
uwiki stats <folder|file>... [--by folder|<frontmatter key>] [--top N] [--json] [--exclude GLOB] [--include GLOB]
uwiki wrap [-w 70] [--check] <file>...
```

`build` writes `<title>.html` and `<title>.md` (title defaults to folder name),
`--html` or `--md` to write only one of them.
Page title is front matter `title`, else the heading page starts with, else file name.
Page header shows it after titles of all its folders, a leading heading repeating it is dropped.

`build`, `check` and `stats` skip hidden files and folders, `node_modules` and `vendor`.
`--exclude` skips more, `--include` takes back skipped or excluded ones, both repeatable.
Glob with `/` matches path from vault root, without it any path segment, like in `.gitignore`,
`**` matches across folders, a matching folder matches everything in it:
`--exclude 'docs/**' --include 'docs/adr/**'`.
Symlinked page pointing into the vault is skipped, links to it lead to its target.

`check` reports unresolved wiki and markdown links and headings, missing images,
frontmatter syntax and list numbering as `path:line: message`, exits 1 if any.

`stats` counts pages, words, lines, headings, list items, wiki and external links and images
outside code, grouped by folder or frontmatter key, e.g. `--by status`.
It lists the largest pages and orphans: pages not linked from the counted ones, folder pages excepted.

`wrap` rewraps paragraphs and list items with lines longer than width (tab counts as 4),
leaving frontmatter, code, tables and headings as is, never splitting wiki links and inline code.
`--check` reports such lines instead and exits 1 if any.

Example:

```
$ uwiki build vault -o out     # out/vault.html and out/vault.md
$ uwiki check vault
vault/Ideas.md:12: unresolved link: [[Roadmap]]
vault/Plans.md:7: list number 3, expected 2
$ uwiki stats vault --by status --top 0
status  pages  words  lines  headings  items  links  external  images
draft      42   9120   1310        58    412    530         3       4
done       17   2804    401        19    150    211         0       1
total      59  11924   1711        77    562    741         3       5
```

Supported Obsidian syntax:

- `[[Page]]`, `[[Page|text]]`, `[[folder/Page]]`, `[[Page#Heading]]`, `[[#Heading]]`
- `![[Page]]`, `![[Page#Heading]]` embeds, `![[image.png]]`, `![[image.png|300]]`
- callouts `> [!note] Title`, foldable `> [!note]-`
- YAML front matter is stripped

Markdown links `[text](../folder/Page.md#heading)` resolve by path relative to the page,
heading by its GitHub/GitLab anchor, so the vault can be plain markdown docs as well.

Folder page is `README.md` (any case), `index.md` or file named as folder, e.g. `Projects/Project.md`.
`README.md` wins over `index.md`, `build` warns and `check` reports when both are present.

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

## Development

```
make test                    # run tests
make patch|minor|major       # test, bump version, commit and tag it
make release                 # push master and the tag
make up                      # install the tagged version with mise
```

The release workflow runs tests on the pushed tag and creates GitHub release,
mise resolves `latest` from releases.

## License

MIT, see [LICENSE](LICENSE).
