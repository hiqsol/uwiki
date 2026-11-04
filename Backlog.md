# Backlog

Planned features in order of implementing, each with what makes it done.
Links resolve the same way in every command, new features reuse the vault resolver, not a copy of it.
Dependencies stay `markdown` only: watching, serving and previews use the standard library and plain JS.

## Page parsed once

A page is parsed once into a cached record: front matter items with their lines, malformed and unclosed
front matter, lines marked as code, headings with GitHub and uwiki anchors, numbered list items with
written and expected numbers, links with kind, position, line and parsed name, heading, item and text.
A link resolves through one `resolve_link` giving page, folder, attachment or none, heading and item found or not,
whether by alias and its anchor.
`check` reports from the record instead of a converter subclass, `Links` and `stats` count from it,
`mv` splices new link text at link positions, `wrap` and `ls` take code lines from it,
list numbering and item anchors share one list walker.
Done when no command but the renderer walks page text itself and the test suite passes unchanged.

## One orphan notion

`check --orphans` warns about pages no chain of links leads to from the root folder page,
naming the reason, `--unlinked` goes as it is the "no page links here" reason, `stats` only counts.
Done when README describes orphans once.

## wrap leaves all code as is

`wrap` takes fenced code and front matter as the other commands do: `~~~` fences, a fence closes
only by its own kind, front matter closing with `...`, unclosed front matter leaves the page as is.
Done when a long line in a `~~~` block is neither rewrapped nor reported.

## README by concepts

Install, then concepts: vault root, folder page, reading order, link resolution, each defined once before use,
then every command in 2–3 lines, config, supported syntax, the HTML page.
Implementation details go: breadth-first walk, temporary folder, debounce, reload script.
Done when "links resolve the same way in every command" is said once.

## HTML is a reading IDE

The one page HTML is a lightweight, fast IDE for humans reading a wiki that is the source others,
agents too, program in, commenting comes later. Everything below runs in the page, no build options.

## Resizable sidebar

Dragging the sidebar edge changes its width, double click restores the default, the page remembers it.
Done when the width survives reload and the content reflows while dragging.

## HTML filter

The search box filters, there are no search results apart from it: sidebar and content show only pages
matching every term, in the reading order of the full page, a folder of a shown page stays in the sidebar greyed.
A word matches pages having it as search matches it now, strong matches only when there are any,
`"Note:"` or `"force discard"` matches the text exactly as written,
`key:value` front matter keys pages have (a list matches any item, a value not matching any exactly
matches by prefix, so typing `scope:co` already shows core), `in:folder` pages under a folder named by path or title,
`-` before any term negates, terms of one key match any of them, all other terms all of them.
A shown page lists under it in the sidebar its sections having the words, with their count,
words are marked in content, Enter and Shift+Enter go to next and previous mark,
Escape clears all but `key:value` and `in:` terms, next Escape clears the box.
A link to a hidden page shows as broken and still previews on hover,
backlinks keep counting all pages, ones from hidden pages greyed.
The box is in the URL, `#q=scope:core deck`, reload keeps it.
Done when `scope:core -status:stub deck` on a vault shows its core pages not stubs having deck,
with deck sections listed under them, and reload keeps it.

## Facet chips

Always under the box: a row for every `[schema]` key listing values, a chip for each value in schema order
with the count of pages it would show with the other terms of the box: `core 108 · duel 20 · advanced 54`,
chips of 0 greyed, a row folds to its key name and the page remembers it.
A click adds or removes its term in the box, chips and typed terms are one filter.
Done when clicking `core` types `scope:core`, `duel` keeps its count, and the counts follow the box.

## Stats line

Under the box: shown out of all pages, words and tokens, `108/228 pages · 10k/54k words · 14k/72k tokens`,
words counted as `stats` counts them, tokens estimated from characters.
Done when the full page line shows the totals `uwiki stats` prints for the same paths.

## Check results in HTML

`build` embeds what `check` with the vault config reports for built pages, without failing on it.
A page header gets a `Problems 2` block like backlinks, the issue marked where it is: link, list item, front matter,
filter `is:problem` shows pages having any, the stats line counts them.
Done when every issue `uwiki check` reports for a built page shows in its page and `is:problem` lists them.

## check: scope layers

`[check] layers.scope = ["core", "duel", "advanced"]` makes values of a front matter key layers:
a page of a layer links only to pages of its layer or earlier ones, pages of other values are outside layers,
a folder page comes no later than any of its pages, so a filtered view never misses its folder page.
`path:line: core page links advanced page: [[Hub]]`.
Done when a core page linking an advanced one and an advanced folder page of a core page are reported.
