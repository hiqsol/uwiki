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

## README by concepts

Install, then concepts: vault root, folder page, reading order, link resolution, each defined once before use,
then every command in 2–3 lines, config, supported syntax, the HTML page.
Implementation details go: breadth-first walk, temporary folder, debounce, reload script.
Done when "links resolve the same way in every command" is said once.

## HTML is a reading IDE

The one page HTML is a lightweight, fast IDE for humans reading a wiki that is the source others,
agents too, program in, commenting comes later. Everything below runs in the page, no build options.

## check: scope layers

`[check] layers.scope = ["core", "duel", "advanced"]` makes values of a front matter key layers:
a page of a layer links only to pages of its layer or earlier ones, pages of other values are outside layers,
a folder page comes no later than any of its pages, so a filtered view never misses its folder page.
`path:line: core page links advanced page: [[Hub]]`.
Done when a core page linking an advanced one and an advanced folder page of a core page are reported.
