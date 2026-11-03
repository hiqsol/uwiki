# uWiki - micro wiki

[![test](https://github.com/hiqsol/uwiki/actions/workflows/test.yml/badge.svg)](https://github.com/hiqsol/uwiki/actions/workflows/test.yml)

Markdown utility for wikis: builds folder of markdown files into single HTML or markdown file,
checks it, lists its pages for LLMs, counts statistics and rewraps long lines.
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
uwiki build <folder|file>... [--title TITLE] [--html] [--md] [-o OUTPUT] [--no-backlinks] [--no-front-matter] [--exclude GLOB] [--include GLOB]
uwiki watch <folder|file>... [build options] [-q] [--interval 0.5]
uwiki serve <folder|file>... [build options] [-p 8000] [--host 127.0.0.1] [--open] [-q] [--interval 0.5]
uwiki check <folder|file>... [--no-folder-links] [--orphans] [--unlinked] [--unlisted] [--exclude GLOB] [--include GLOB]
uwiki llms <folder|file>... [--title TITLE] [-o FILE] [--summary TEXT] [--check] [--exclude GLOB] [--include GLOB]
uwiki ls <folder|file>... [--external] [-z] [--exclude GLOB] [--include GLOB]
uwiki stats <folder|file>... [--by folder|<frontmatter key>] [--top N] [--json] [--exclude GLOB] [--include GLOB]
uwiki wrap <folder|file>... [-w 70] [--check] [--exclude GLOB] [--include GLOB]
```

Every command takes folders and files of one or more vaults.
Vault root of a path is the nearest folder with `.obsidian`, else the folder all given paths share,
pages keep their folders from it and links resolve in the whole vault.

`build` writes given paths into one `<title>.html` and one `<title>.md`.
`-o` is a folder to write them in, default: current, or a file name:
`-o out/Wiki` writes both, `-o out/Wiki.html` or `-o out/Wiki.md` only one,
`--html` or `--md` writes only one of them otherwise.
Title defaults to the name of the one folder built, else to the `-o` file name,
`-o` is required for several paths.
Folders on the way to built pages show by their titles only,
a link or embed from built pages to a vault page left out fails the build with `path:line: message`.
Page title is front matter `title`, else the heading page starts with, else file name.
Page header shows it after titles of all its folders, a leading heading repeating it is dropped.
Under every page "Linked from" lists built pages linking to it by title, in HTML and markdown,
wiki and markdown links and embeds count, links from a page to itself and from code do not,
a link to a heading shows it: `Rules › Phases`. `--no-backlinks` leaves the list out.

`watch` builds, then builds again on change of any page or attachment the vault takes,
added, deleted and renamed ones too, polling every `--interval` seconds, changes close together make one build.
Each build prints time, pages and outputs, `-q` errors only;
a failed build prints why and keeps the last good output, watching goes on.

`serve` watches the same way and serves the HTML on `http://127.0.0.1:8000`,
`--host 0.0.0.0` serves other hosts too, `-p 0` picks a free port, `--open` opens the page after the first build.
The page reloads after a rebuild keeping its scroll position and search, `build` output never gets this script.
Output goes to a temporary folder removed on exit unless `-o` is given, attachments are served from the vault.

Pages of a folder go in reading order, the same in `build`, `llms` and the HTML sidebar:
folder page first, then pages it links in the order of its links, so it serves as contents,
every other page right after the first page linking it, recursively,
so related pages stay together and general goes before specific.
Pages no page of the folder links go by first reach in a breadth-first walk of links
from the root folder page, unreachable ones last, by name.
A link into a subfolder counts for the subfolder, a subfolder links what its folder page does.

Commands skip hidden files and folders, `node_modules` and `vendor`.
`--exclude` skips more, `--include` takes back skipped or excluded ones, both repeatable.
Glob with `/` matches path from vault root, without it any path segment, like in `.gitignore`,
`**` matches across folders, a matching folder matches everything in it:
`--exclude 'docs/**' --include 'docs/adr/**'`.
Symlinked page or folder pointing into the vault is skipped, links through it lead to its target.

`check` reports unresolved wiki and markdown links and headings, missing images,
frontmatter syntax and list numbering as `path:line: message`, exits 1 if any.
Every relative markdown link, inline or reference, must name an existing file or folder
inside the vault, spelled as on disk, absolute links are reported.
`--no-folder-links` reports links to folders, `--orphans` reports pages
no chain of links leads to from the root folder page (any link, without one),
`--unlinked` warns about pages no other page links to, `--unlisted` about pages
their folder page does not link, both without changing exit code.
Links count from every page of the vault, checked or not.

`llms` writes [llms.txt](https://llmstxt.org) (default: in the one folder listed, else `-o` is required):
title (default: the folder name), `--summary` as quote
(default: front matter `description` of the folder page of the folder given paths share), then a section per folder
listing its pages as `- [title](path): description`, links relative to the output file.
Pages go in reading order.
`--check` exits 1 if the file is out of date instead of writing it.

`ls` lists markdown files the other commands take, one per line, `-z` ends them with NUL instead.
`--external` lists unique http and https links outside front matter and code instead.
So other tools check the same files, e.g. with versions pinned by [mise](https://mise.jdx.dev) tasks:

```
uwiki ls -z docs | xargs -0 markdownlint-cli2
uwiki ls -z docs | xargs -0 typos
uwiki ls --external docs | lychee -
```

`stats` counts pages, words, lines, headings, list items, wiki and external links and images
outside code, grouped by folder or frontmatter key, e.g. `--by status`.
It lists the largest pages and orphans: pages not linked from the counted ones, folder pages excepted.

`wrap` rewraps paragraphs and list items with lines longer than width (tab counts as 4),
leaving frontmatter, code, tables and headings as is, never splitting wiki links and inline code.
`--check` reports such lines instead and exits 1 if any,
a line rewrapping leaves as is, e.g. a long URL or inline code, is not reported.

Example:

```
$ uwiki build vault -o out     # out/vault.html and out/vault.md
$ uwiki build vault/docs vault/adr -o out/Docs.html
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
- YAML front matter is stripped from text, HTML shows it next to page title

Wiki link name resolves to a page before a folder without folder page,
then to one nearer the linking page, then to the shortest path.

Markdown links `[text](../folder/Page.md#heading)` resolve by path relative to the page,
heading by its GitHub/GitLab anchor (repeated heading gets `-1`, `-2`...),
so the vault can be plain markdown docs as well.
Link text may wrap across lines, reference links `[text][ref]` resolve via their `[ref]: path.md`.

Folder page is `README.md` (any case), `index.md` or file named as folder, e.g. `Projects/Project.md`.
`README.md` wins over `index.md`, `build` warns and `check` reports when both are present.

The HTML page is self-contained, light or dark by system preference:

- sidebar with collapsible contents following the page being read, expand or collapse all at once
- hover preview of a link target: its page or `#heading` section in a popover, cloned from the page,
  so it works from `file://`; links in it preview too, 3 levels deep; `Esc` closes, the title follows the link;
  touch devices get no popover, a tap follows the link
- front matter in a block right of page title, folded into one line of values, `▸` unfolds a table
  of all keys and values the text flows around, under the title on narrow screens;
  `--no-front-matter` leaves it out
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
problems = uwiki.check(['docs'], options=uwiki.CheckOptions(orphans=True))
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
