# Backlog

Planned features in order of implementing, each with what makes it done.
Links resolve the same way in every command, new features reuse the vault resolver, not a copy of it.
Dependencies stay `markdown` only: watching, serving and previews use the standard library and plain JS.

## P2 Reading order of pages in a folder

- a) One order for `build`, `llms` and the HTML sidebar, alphabetical order does not help a reader in a small folder
- b) Folder page first, then pages it links in the order of its links, the author keeps it as contents
- c) Every other page goes right after the first page of the folder linking it, recursively,
  so related pages stay together and general goes before specific: Star › IPS › Slot › Space › Asteroids
- d) Pages no page of the folder links go by first reach in a breadth-first walk of links from the root page,
  closer to the start is more basic, also for folders without folder page
- e) Pages unreachable from the root go last, by name
- f) `check --unlisted` warns about pages the folder page does not link, without changing exit code

## P3 Backlinks

- a) `build` HTML shows under every page "Linked from": pages linking to it, by title, each a link
- b) Wiki and markdown links count, embeds too, links from a page to itself and from code do not
- c) A link to a heading counts for its page, the list shows the heading: `Turn › Phases`
- d) `build` markdown output gets the same list, so the single `.md` file reads the same way
- e) `--no-backlinks` turns it off

## P4 Front matter block

- a) `build` HTML shows front matter in a block floating right, its top level with the page title
- b) Folded by default, one line as tall as the title: values in order, joined by ` · `, lists by `, `,
  cut with an ellipsis, ▸ unfolds
- c) Unfolded it grows down as needed into a table of all keys and values, title included,
  the page text flows around it, ▾ folds back
- d) Narrow screens: the block stops floating and sits under the title, folded too
- e) Pages without front matter get no block, `--no-front-matter` turns it off

## P5 Hover preview

- a) Hovering a vault link in HTML shows a popover with the target page, or its section for `#heading`
- b) Content is cloned from the same HTML page, nothing is fetched, so it works from `file://`
- c) Opens after a short delay, stays while the pointer is over it, closes on leave and `Esc`
- d) Links inside a popover preview too, nested up to 3 levels
- e) Long targets are cut to a fixed height with a fade, a click on the popover title follows the link
- f) Touch devices: no popover, a tap follows the link as now

## P6 watch command

- a) `uwiki watch <folder|file>... [build options]` builds once, then rebuilds on change of any file
  `build` takes: markdown, images and other attachments, after the skip list, `--include` and `--exclude`
- b) Polling of mtimes and file lists, no dependency; added, deleted and renamed files count
- c) Changes within a short interval are debounced into one build
- d) A failed build prints the error and keeps watching, the last good output stays
- e) Each build prints time, pages and output paths, `-q` prints errors only

## P7 serve command

- a) `uwiki serve <folder|file>... [build options] [-p 8000] [--host 127.0.0.1]` watches as P6 and
  serves the built HTML with `http.server`
- b) Live reload: the page reloads after a rebuild and keeps its scroll position and search,
  the reload script is added only when served, never to `build` output
- c) Binds to localhost by default, `--host 0.0.0.0` exposes it on purpose
- d) `--open` opens the page in the browser after the first build
- e) Output goes to a temporary folder unless `-o` is given, so serving leaves no files behind

## P8 Front matter schema

- a) Config `uwiki.toml` in the vault root, or `[tool.uwiki]` in `pyproject.toml`, read by every command
- b) Schema declares allowed keys, required keys and allowed values or a value type per key:
  `status = ["stub", "draft", "stable"]`, `date = "date"`, `aliases = "list"`
- c) Rules can apply to folders: `[schema."docs/**"]`
- d) `check` reports unknown keys, missing required keys and values out of the schema
- e) Config can also hold defaults of command options, e.g. `exclude`, used by P6 and P7

## P9 Aliases

- a) Front matter `aliases: [VP, VPs]` makes `[[VP]]` resolve to the page, in every command
- b) A page name wins over an alias of another page, `check` reports such clashes and aliases
  shared by two pages
- c) `[[VP]]` keeps its text `VP` in HTML and markdown output, the link leads to the page
- d) Search in HTML finds a page by its aliases

## P10 Numbered list item anchors

- a) Every item of a numbered list gets an anchor by its number path: `#3`, nested `#3.2`
- b) `[[Star#3]]` and `[text](Star.md#3)` link to item 3 of the first numbered list of Star,
  `[[Star#Heading#3]]` to item 3 under Heading
- c) `check` reports links to missing items, as for missing headings
- d) HTML shows the number on hover with a copy link, as headings do in GitHub
- e) GitHub renders no such anchors: README notes that such markdown links open the page only

## P11 Unlinked mentions

- a) `check --mentions` warns about a page title or alias used as plain text without a link,
  without changing exit code, as `--unlinked` does
- b) Only the first mention per page is reported, later ones may stay plain
- c) Whole words only, case sensitive by default, mentions in code, headings and link text skipped
- d) A page mentioning itself is no mention
- e) Config (P8) can list terms to ignore and a minimum term length

## P12 mv command

- a) `uwiki mv <from> <to>`, the one command not taking `<folder|file>...`, moves or renames a page, folder or attachment inside the vault and
  rewrites every link to it: wiki links, markdown links, embeds and reference definitions
- b) Relative markdown links inside moved pages are rewritten for their new place
- c) Wiki links change only when they stop resolving to the moved target or would resolve
  elsewhere, name only links stay name only when still unique
- d) Uses `git mv` inside a git work tree, plain rename otherwise
- e) `--dry-run` prints the move and every changed line, `check` on the vault passes after a move
  if it passed before
