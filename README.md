# uWiki - micro wiki

[![test](https://github.com/hiqsol/uwiki/actions/workflows/test.yml/badge.svg)](https://github.com/hiqsol/uwiki/actions/workflows/test.yml)

Markdown utility for Obsidian vaults and plain markdown docs: builds a vault into one HTML or markdown file,
serves it rebuilding on change, checks it, counts it, links mentions, rewraps lines, moves pages rewriting links,
and is a language server for editors.

## Installation

Python 3.11 or later, with [mise](https://mise.jdx.dev) or [uv](https://docs.astral.sh/uv/):

```
mise use -g pipx:hiqsol/uwiki
uv tool install git+https://github.com/hiqsol/uwiki
```

## Concepts

**Vault**: folder of markdown pages, rooted at the nearest folder with `.obsidian`, else the one given paths share.
Commands take its folders and files, skipping hidden ones, `node_modules` and `vendor`,
`--exclude GLOB` skips more, `--include GLOB` takes back, globs as in `.gitignore`.

**Folder page**: `README.md`, `index.md` or page named as its folder, the contents of the folder.

**Reading order** of `build`, `llms` and the HTML sidebar: folder page, then pages in the order it links them,
every other page right after the first page linking it, unlinked ones last.

**Links** resolve the same way in every command:

- `[[Page]]` by name, then by front matter `aliases`, nearest first; `[[Page|text]]`, `[[folder/Page]]`
- `[[Page#Heading]]`, `[[Page#3]]` item 3 of the first numbered list of Page, `[[Page#Heading#3]]` under Heading
- `[text](../Page.md#heading)` by path relative to the page, heading by its GitHub anchor
- embeds `![[Page]]`, `![[Page#Heading]]`, `![[image.png|300]]`, callouts `> [!note] Title`

**Orphan**: page no chain of links leads to from the root folder page.

## Commands

```
uwiki build  <paths> [-o OUTPUT] [--title TITLE] [--html | --md] [--no-backlinks] [--no-front-matter]
uwiki watch  <paths> [build options] [-q] [--interval 0.5]
uwiki serve  <paths> [watch options] [-p 8000] [--host 127.0.0.1] [--open]
uwiki check  <paths> [--orphans] [--unlisted] [--mentions] [--no-folder-links] [--max-lines N]
uwiki link   <paths> [--dry-run] [-w 70]
uwiki llms   <paths> [-o FILE] [--title TITLE] [--check]
uwiki index  <paths> [--check]
uwiki ls     <paths> [--external] [-z]
uwiki stats  <paths> [--by folder|KEY] [--top N] [--json]
uwiki wrap   <paths> [-w 70] [--check]
uwiki mv     <from> <to> [--dry-run]
uwiki lsp
```

`uwiki <command> --help` lists all options.

- `build` writes `<title>.html` and `<title>.md`, `-o out/Wiki.html` only one;
  a page shows its folders, backlinks and front matter; a link to a page left out fails the build
- `watch` builds again on change, `serve` also serves the HTML on `http://127.0.0.1:8000`, reloading the page,
  its blocks with `data-line` of the source line they start at;
  both restart on change of uwiki's own code, as on upgrade, unless it fails to import
- `check` reports unresolved links, headings and items, missing images, front matter out of `[schema]`
  and list numbering as `path:line: message`, exits 1 if any;
  `--orphans` reports orphans, `--unlisted` and `--mentions` warn about pages their folder page does not link
  and plain text mentions of page titles, `--max-lines` reports longer pages
- `link` links the plain text mentions `check --mentions-every` warns about: `[[Star]]s`
- `llms` writes [llms.txt](https://llmstxt.org): a section per folder of `- [title](path): description`
- `index` fills `<!-- generated: NAME -->` ... `<!-- /generated -->` blocks of pages
  with the other pages of their folder, `- [title](path): description` each,
  keeping their order and the lines linking subfolders, `--check` reports blocks out of date
- `ls` lists the files commands take, `--external` external links, for other tools:
  `uwiki ls -z docs | xargs -0 typos`, `uwiki ls --external docs | lychee -`
- `stats` counts pages, words, lines, headings, items, links and images by folder or front matter key
- `wrap` rewraps paragraphs and list items longer than `-w 70`, `--check` reports them
- `mv` moves a page, folder or attachment rewriting every link to it, with `git mv` in a git work tree
- `lsp` serves definition, hover, references, outline, completion and check diagnostics over stdio;
  Neovim 0.11+:

```lua
vim.lsp.config('uwiki', { cmd = { 'uwiki', 'lsp' }, filetypes = { 'markdown' }, root_markers = { 'uwiki.toml' } })
vim.lsp.enable('uwiki')
```

## Config

`uwiki.toml`, or `[tool.uwiki]` in `pyproject.toml`, in the vault root or the nearest folder above it
up to the git work tree root, holds option defaults:
top level ones for every command, a table for a command, `[build]` also for `watch` and `serve`.
`[schema]` gives front matter keys `check` takes, dotted ones nested in a map or in every map of a list,
`[schema."glob"]` adds rules for pages the glob matches from the config folder, `_inherit = false` drops the ones before.
`[check] layers` makes values of a key layers:
a page links only to pages of its layer or earlier ones, a folder page comes no later than its pages.

```toml
exclude = ["drafts"]

[check]
orphans = true
mentions = true
mentions-ignore = ["Go"]
max-lines = 1500                          # a page an agent reads in one go
max-lines-ignore = ["log.md"]             # globs from the config folder
layers.scope = ["core", "duel", "advanced"]

[index.adrs]                              # <!-- generated: adrs --> blocks
line = "* [{title}]({path}), {date}: {description}"   # {front matter key}, {title}, {stem}, {path}
sort = "-date"                            # by key, descending; else lines keep their order
empty = "None yet."
exclude = ["log.md"]

[schema]                                  # keys in the order HTML shows them
_required = ["status"]
status = ["stub", "draft", "stable"]      # allowed values
date = "date"                             # or a type: string, number, bool, date, datetime, page, list, any
supersedes = "page"                       # names a page as links do: Page, [[Page]], ../Page.md
generated.at = "datetime"                 # generated: { by: me, at: 2026-01-02T03:04:05Z }

[schema."docs/**"]                        # folder rules add to the top level ones
owner = "string"

[schema."**/index.md"]
_inherit = false                          # folder pages: no keys required, none allowed
```

## HTML page

One self-contained file, light or dark by system preference, works from `file://`:

- pages render as GitHub and Obsidian show them: CommonMark with tables, task lists and strikethrough;
  a page is laid out and drawn as it nears the window, so a long vault opens fast
- sidebar of contents following the page being read, its edge drags its width,
  a click on a branch title folds or unfolds it too; guide lines show nesting, the one of the page
  being read stands out; tokens of a branch with all pages under it right of its title, of a page on hover
- hover preview of a link target under the folders it is in, links in it preview too,
  sidebar entries beside the sidebar
- front matter, backlinks and what `check` reports top right of page header, problems marked at their lines;
  nested front matter keys beside the key above them in the same table
- `/` focuses the box filtering pages: words, `"exact text"`, `key:value` front matter, `in:folder`,
  `is:problem`, `-term`, e.g. `scope:core -status:stub deck`; `Enter` goes to the next match,
  the box goes to the URL as `?q=`
- chips of `[schema]` values with page counts, a click adds or removes one
- pages, words and tokens shown out of all
- code blocks highlighted by Prism and `mermaid` blocks drawn as they near the window, the libraries
  loaded from CDNs on first need; offline, code stays plain

## Development

```
make test                    # run tests
make patch|minor|major       # test, bump version, commit and tag it
make release                 # push master and the tag, the release workflow publishes it
make up                      # install the tagged version with mise
```

## License

MIT, see [LICENSE](LICENSE).
