# Config

`uwiki.toml`, or `[tool.uwiki]` in `pyproject.toml`, in the vault root or the nearest folder above it
up to the git work tree root, holds option defaults:
top level ones for every command, a table for a command, `[build]` also for `watch` and `serve`.
Its globs match from its folder: `exclude = ["data"]` leaves out all of `data/`, run on it or below too.

`--require-config`, or `UWIKI_REQUIRE_CONFIG=1` in the environment, makes a command refuse to run without a config:
run from a wrong folder, `link` and `wrap` would rewrite every page below it with no excludes.

## Schema

`[schema]` gives front matter keys `check` takes, dotted ones nested in a map or in every map of a list,
`_required` the ones a page has, a map key every key nested in it,
`[schema."glob"]` adds rules for pages the glob matches from the config folder, `_inherit = false` drops the ones before.
The HTML page shows keys in schema order as a tree of their values, values nested with slashes under their group.

## Refs

`[refs."P:"]` makes `P:24` a [ref](Concepts.md#refs), linking where the vault defines it,
`url` with `{id}` where it leads when the vault does not, `id` a regex the ids match;
a prefix ends in its separator, `:` or `-`:

```toml
[refs."P:"]                               # P:24 links to **P:24.** starting an item
[refs."HQD-"]
url = "https://jira.example.com/browse/HQD-{id}"
id = "[0-9]+"                             # HQD-NNN stays text
```

Schema type `ref` takes refs that lead somewhere: `sources = "ref"`.

## Layers

`[check] layers` makes values of a key layers:
a page links only to pages of its layer or earlier ones, a folder page comes no later than its pages.

## Example

```toml
exclude = ["drafts"]

[check]
orphans = true
mentions = true
mentions-ignore = ["Go"]                  # terms
mentions-exclude = ["prompts/**"]         # pages, globs from the config folder
max-lines = 1500                          # a page an agent reads in one go
max-lines-ignore = ["log.md"]             # globs from the config folder
acyclic = ["supersedes", "superseded_by"] # no chain of these page valued keys leads back
inverse.supersedes = "superseded_by"      # a page B supersedes names B in superseded_by, and back
stale-days = 183                          # warn when the latest of these dates is older
stale-date = ["verified.at", "generated.at"]
stale-until = "stale_after"               # warn once this date has come
code-paths."skills/**/map.md" = "docs"    # `a/b.md` in such pages names docs/a/b.md
layers.scope = ["core", "duel", "advanced"]

[refs."adr:"]                             # adr:12 links to the page with front matter id: adr:12
[refs."SD-"]
url = "https://jira.example.com/browse/SD-{id}"

[index.adrs]                              # <!-- generated: adrs --> blocks
line = "* [{title}]({path}), {date}: {description}"   # {front matter key}, {title}, {stem}, {path}
sort = "-date"                            # by key, descending; else lines keep their order
empty = "None yet."
exclude = ["log.md"]

[schema]                                  # keys in the order HTML shows them
_required = ["status"]
status = ["stub", "draft", "stable"]      # allowed values
date = "date"                             # or a type: string, number, bool, date, datetime, page, ref, list, any
description = "string(250)"               # string of at most 250 characters
supersedes = "page"                       # names a page as links do: Page, [[Page]], ../Page.md
generated.at = "datetime"                 # generated: { by: me, at: 2026-01-02T03:04:05Z }

[schema."docs/**"]                        # folder rules add to the top level ones
owner = "string"

[schema."**/index.md"]
_inherit = false                          # folder pages: no keys required, none allowed
```

This repo itself has `[tool.uwiki]` in its `pyproject.toml`, leaving the test fixtures out of its build,
and `tests/fixtures/pyproject.toml` an empty one, so each fixture vault is a vault of its own.
