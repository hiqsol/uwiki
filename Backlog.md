# Backlog

Planned features in order of implementing, each with what makes it done.
Links resolve the same way in every command, new features reuse the vault resolver, not a copy of it.
Dependencies stay `markdown` only: watching, serving and previews use the standard library and plain JS.

## In-process tests

Tests call `cli.main()` in the test process, patching `sys.argv` and capturing output and exit code,
one subprocess smoke test stays, watch and serve tests wait on output lines instead of fixed sleeps.
Done when the suite runs in under 5 seconds, now 17.

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

## serve writes HTML only

`serve` without `-o` writes only the HTML it serves into the temporary folder, a quarter of every rebuild now.
Done when `serve` prints one output and the test expects it.

## Fewer output options

Output kind comes from `-o` alone: no extension writes both, `.html` or `.md` one, `--html` and `--md` go.
`llms` becomes an output of `build`, e.g. `-o llms.txt`, with the same title and output rules,
`--check` reports any output out of date, `--summary` goes, the folder page description stays.
Done when `Build.targets` holds the only output rules and README lists them once.

## No watch command

`serve -o out` does what `watch` does, `watch` goes with its config table rule.
Done when README, `cli.py` and `config.py` mention only `build` and `serve`.

## Fewer features

- mentions: `--mentions` stays, ignored terms and minimum length move to config only, matching is case sensitive
- item anchors: `[[Page#3]]` stays, items of lists under headings `[[Page#Heading#3]]` go
- hover preview: one level instead of three

Done when each removed option is gone from `cli.py`, README and tests.

## README by concepts

Install, then concepts: vault root, folder page, reading order, link resolution, each defined once before use,
then every command in 2–3 lines, config, supported syntax, the HTML page.
Implementation details go: breadth-first walk, temporary folder, debounce, reload script.
Done when "links resolve the same way in every command" is said once.
