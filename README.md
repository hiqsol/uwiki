# uWiki - micro wiki

[![test](https://github.com/hiqsol/uwiki/actions/workflows/test.yml/badge.svg)](https://github.com/hiqsol/uwiki/actions/workflows/test.yml)

Markdown utility for wikis: builds folder of markdown files into single HTML or markdown file,
rebuilds and serves it on change, checks it, lists its pages for LLMs, counts statistics,
rewraps long lines and moves pages rewriting links to them.
Links resolve the same way in every command. I use it for Obsidian vaults.

## Installation

Needs Python 3.11 or later. With [mise](https://mise.jdx.dev):

```
mise use -g pipx:hiqsol/uwiki
```

Or with [uv](https://docs.astral.sh/uv/):

```
uv tool install git+https://github.com/hiqsol/uwiki
```

## Usage

```
uwiki <command> <folder|file>... [--exclude GLOB] [--include GLOB] [options]
uwiki mv <from> <to> [--dry-run] [--exclude GLOB] [--include GLOB]
uwiki lsp

build  [--title TITLE] [-o OUTPUT] [--html | --md] [--no-backlinks] [--no-front-matter]
watch  [build options] [-q] [--interval 0.5]
serve  [watch options] [-p 8000] [--host 127.0.0.1] [--open]
check  [--no-folder-links] [--orphans] [--unlisted] [--mentions [--mentions-every] [--mentions-self-bold]]
link   [--dry-run] [-w 70] [--mentions-ignore TERM] [--mentions-min-length 3] [--mentions-ignore-case] [--mentions-self-bold]
llms   [--title TITLE] [-o FILE] [--summary TEXT] [--check]
ls     [--external] [-z]
stats  [--by folder|KEY] [--top N] [--json]
wrap   [-w 70] [--check]
```

Every command takes folders and files of one or more vaults.
Vault root of a path is the nearest folder with `.obsidian`, else the folder all given paths share,
pages keep their folders from it and links resolve in the whole vault.

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
"Backlinks" lists built pages linking to a page by title: under the page in markdown,
in HTML as a block top right of page header over front matter, folded into one line of their count and titles.
Wiki and markdown links and embeds count, links from a page to itself and from code do not,
a link to a heading shows it: `Rules › Phases`. `--no-backlinks` leaves the list out.

`watch` builds, then builds again on change of any page or attachment the vault takes,
added, deleted and renamed ones too, polling every `--interval` seconds, changes close together make one build.
Each build prints time, pages and outputs, `-q` errors only;
a failed build prints why and keeps the last good output, watching goes on.

`serve` watches the same way and serves the HTML on `http://127.0.0.1:8000`,
`--host 0.0.0.0` serves other hosts too, `-p 0` picks a free port, `--open` opens the page after the first build.
The page reloads after a rebuild keeping its scroll position and search, `build` output never gets this script.
HTML only goes to a temporary folder removed on exit unless `-o` is given, attachments are served from the vault.

`check` reports unresolved wiki and markdown links and headings, missing images,
frontmatter syntax and list numbering as `path:line: message`, exits 1 if any.
Every relative markdown link, inline or reference, must name an existing file or folder
inside the vault, spelled as on disk, absolute links are reported.
`--no-folder-links` reports links to folders, `--orphans` reports orphans: pages
no chain of links leads to from the root folder page (any link, without one), naming the reason:
`no page links here` or `not reachable from index.md`, `--unlisted` warns about pages
their folder page does not link, `--mentions` about the first plain text mention of a page title or alias
in a page not linking it, `--mentions-every` about every one, all without changing exit code.
Mentions are whole words and their plurals (`Stars`, `Classes`, `Ancestries`), with the first letter as written
and the rest in any case (`Force discard` mentions `Force Discard`) unless `--mentions-ignore-case`,
outside code, headings, link text and bold, which defines a term rather than mentions it,
at least `--mentions-min-length 3` long, `--mentions-ignore TERM` skips one, a page mentioning itself is no mention.
An ignored name that is no title or alias, e.g. a game title `Star Realms`, keeps the terms in it plain,
also wrapped to the next line. `--mentions-self-bold` warns about a mention of the page itself not in bold:
on its own page a term is bold, not linked, so terms stand out from plain words.
Links count from every page of the vault, checked or not.
Config `[check] layers.scope = ["core", "duel", "advanced"]` makes values of a front matter key layers:
a page of a layer links only to pages of its layer or earlier ones,
`rules/Core.md:4: core page links duel page: rules/Duel.md`,
a folder page but the root one comes no later than any of its pages, so a filter by layer keeps it;
pages of other values are outside layers, links to and from them go unchecked.

`llms` writes [llms.txt](https://llmstxt.org) (default: in the one folder listed, else `-o` is required):
title (default: the folder name), `--summary` as quote
(default: front matter `description` of the folder page of the folder given paths share), then a section per folder
listing its pages as `- [title](path): description`, links relative to the output file.
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
It lists the largest pages and counts orphans `check --orphans` reports.

`wrap` rewraps paragraphs and list items with lines longer than width (tab counts as 4),
leaving frontmatter, code, tables and headings as is, never splitting wiki links and inline code.
`--check` reports such lines instead and exits 1 if any,
a line rewrapping leaves as is, e.g. a long URL or inline code, is not reported.

`link` links every mention `check --mentions-every` reports, as `[[Star]]`, `[[Star]]s`,
`[[Warp orbit]]` for alias `Warp Orbit`, as names match in any case, `[[ForceDiscard|Force discard]]`,
in a table cell `[[ForceDiscard\|Force discard]]`, as Obsidian escapes the pipe there,
and rewraps paragraphs it makes longer than `-w 70`, as `wrap` does.
With `--mentions-self-bold` it makes a page's mentions of itself bold, `**Star**` on the Star page.
It takes mention options of the `[check]` config table,
`--dry-run` prints every changed line instead, before and after.

`mv` moves or renames a page, folder or attachment inside the vault, `<to>` may be a folder to move into,
and rewrites every link to it: wiki links, embeds, markdown links and reference definitions.
Unlike other commands, vault root is the nearest folder with `.obsidian`, else the current folder.
Relative markdown links in moved pages are fixed for their new folder.
A path with `/` named as whole inline code or link text follows too, relative to the page or the vault root,
e.g. `docs/` or `[docs/Guide.md](docs/Guide.md)`; other code, prose and non-markdown files stay as they are.
Files the config or `--exclude` leave out, e.g. a built wiki, keep their text.
A wiki link changes only when it would no longer lead where it did, to the shortest name leading right,
so a name only link stays name only when the name is still unique.
Inside a git work tree it moves with `git mv`, else renames.
`--dry-run` prints the move and every changed line instead, `-` before and `+` after.

`lsp` is a language server over stdio for editors, its vault root is the folder the editor opens,
links resolve as in every other command, the vault config `exclude`, `include` and `check` options apply.
Go to definition leads to the page, heading or item a wiki or markdown link names, hover shows it,
an item with its nested ones; completion after `[[` gives page and folder names and aliases,
after `[[Page#` its headings and items with their text, after `[[Page#Heading#` items under Heading.
References of a link, or of the page, heading or item at the cursor, list the lines linking there.
Outline gives headings with the items links can name nested under them.
Diagnostics are what `check` reports, published for the whole vault on start and on every save.
Neovim 0.11+:

```lua
vim.lsp.config('uwiki', { cmd = { 'uwiki', 'lsp' }, filetypes = { 'markdown' }, root_markers = { 'uwiki.toml' } })
vim.lsp.enable('uwiki')
```

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

## Config

`uwiki.toml` in the vault root, or `[tool.uwiki]` in its `pyproject.toml`, holds defaults of command options:
top level ones for every command taking them, a command table for that command,
`[build]` also for `watch` and `serve`. Command line adds to lists and overrides the rest.
`--no-x` flags are given as `x = false`. Schema of front matter is `[schema]`, `check` reports
unknown keys, missing required keys and values out of the schema:

```toml
exclude = ["drafts"]

[check]
unlisted = true
mentions = true
mentions-ignore = ["Go", "Notes"]
mentions-min-length = 4
layers.scope = ["core", "duel", "advanced"]  # config only

[build]
backlinks = false

[schema]                                  # keys in the order build shows them
_required = ["status"]                    # required keys
status = ["stub", "draft", "stable"]      # a list gives allowed values
date = "date"                             # or a type: string, number, bool, date, list, any
aliases = "list"

[schema."docs/**"]                        # folder rules add to the top level ones, glob as --exclude
_required = ["owner"]
owner = "string"
```

Supported Obsidian syntax:

- `[[Page]]`, `[[Page|text]]`, `[[folder/Page]]`, `[[Page#Heading]]`, `[[#Heading]]`
- `[[Page#3]]`, `[[Page#3.2]]` link item 3, or nested item 2 of item 3, of the first numbered list of Page,
  `[[Page#Heading#3]]` of the first one under Heading, `[text](Page.md#3)` too, `check` reports missing items;
  such a link shows as written: `Page#3`, `Page#Heading#3`, `#3` on the same page;
  HTML shows the number of an item on hover, a click copies the link to it.
  GitHub renders no such anchors, so there such markdown links open the page only
- `![[Page]]`, `![[Page#Heading]]` embeds, `![[image.png]]`, `![[image.png|300]]`
- callouts `> [!note] Title`, foldable `> [!note]-`
- YAML front matter is stripped from text, HTML shows it next to page title

Wiki link name resolves to a page, then to a page with it in front matter `aliases: [VP, VPs]`,
then to a folder without folder page, nearer the linking page first, then by the shortest path,
the same in every command. `[[VP]]` keeps its text `VP`, HTML search finds a page by its aliases.
An alias in bold in a numbered list item, e.g. `2. **Tile**: a piece of the Field` under `aliases: [Tile]`,
leads to that item: `[[Tile]]` is `[[Component#2]]`, the item gets the anchor `component--tile` too.
`check` reports an alias another page has as name, so links lead there, and an alias two pages share.

Markdown links `[text](../folder/Page.md#heading)` resolve by path relative to the page,
heading by its GitHub/GitLab anchor (repeated heading gets `-1`, `-2`...),
so the vault can be plain markdown docs as well.
Link text may wrap across lines, reference links `[text][ref]` resolve via their `[ref]: path.md`.

Folder page is `README.md` (any case), `index.md` or file named as folder, e.g. `Projects/Project.md`.
`README.md` wins over `index.md`, `build` warns and `check` reports when both are present.

The HTML page is self-contained, light or dark by system preference:

- sidebar with collapsible contents following the page being read, expand or collapse all at once
- sidebar edge drags its width, a double click restores it, the browser remembers it
- hover preview of a link target: its page or `#heading` section in a popover, cloned from the page,
  so it works from `file://`; links in it preview too, 3 levels deep; `Esc` closes, the title follows the link;
  touch devices get no popover, a tap follows the link
- front matter in a block top right of page header, right of its folder crumb, keys in `[schema]` order,
  folded into one line of values, `▸` unfolds a table of all keys and values the text flows around,
  under the title on narrow screens;
  `--no-front-matter` leaves it out
- search box filters: press `/` or `Ctrl+K`, sidebar and text show only pages matching all its terms,
  in reading order, folders of shown pages stay by title, greyed:
  a word matches by fuzzy full text search, tolerating typos and abbreviations, `"exact text"` as written,
  `key:value` front matter (a list by any item, a value no page has exactly by prefix: `scope:co`),
  `in:folder` pages under a folder by path or title, `is:problem` pages check reports, `-` before a term negates;
  terms of one key match any of them, all other terms all of them: `scope:core scope:duel -status:stub deck`;
  sections having the words list under their page in the sidebar with counts, words are highlighted in text,
  `Enter` and `Shift+Enter` go to next and previous one, `Esc` drops words, next `Esc` the rest;
  links to pages filtered out are struck out and still preview, backlinks from them greyed;
  the box goes to the URL as `?q=`, so a link or reload shows the same pages
- stats line under the box: shown out of all pages, words as `stats` counts them and tokens, 4 characters each,
  and problems
- what `check` with the vault config reports for a page in a block top right of its header over backlinks,
  folded into one line of messages unfolding into links to where they are: `⚠` at the start of the line,
  hover shows the message, front matter ones mark front matter; problems red, warnings orange
- a row of chips for every front matter key `[schema]` lists values of, a chip for each value with the count
  of pages it shows with the other terms, a click adds or removes it, a click on the key folds the row

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
