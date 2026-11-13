# Backlog

Planned features in order of implementing, each with what makes it done.
Links resolve the same way in every command, new features reuse the vault resolver, not a copy of it.
Dependencies stay `markdown-it-py` and `linkify-it-py` only: watching, serving and previews use the standard library and plain JS.

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

## References

A wiki over a database or a tracker cites records by id, as `doc:245` or `SD-2345`, the text the database,
front matter and agents use too. `[refs]` names prefixes and where their ids lead, the text stays as written:
uwiki links it when rendering and never rewrites it as `link` does mentions, so `sources: [doc:245]` stays a value.

```toml
[refs."doc:"]                             # the prefix as written, separator included
page = "Documents"                        # resolved as [[Documents]]
row = "id"                                # the table row whose id cell is the ref's id
[refs."visit:"]
page = "visits/{id}"                      # a page per record
[refs."SD-"]
url = "https://jira.example.com/browse/SD-{id}"
```

- A ref is a configured prefix not after a word character, then an id of word characters, `.`, `-` and `:`
  ending in a word character: `ai:claude-code:1a2b3c4d` is id `claude-code:1a2b3c4d` when `ai:` is a prefix.
  Only configured prefixes match, so COVID-19 and B-12 stay text; none match in code, links and URLs.
- Refs in front matter string and list values link in the front matter table and are checked too.
- `row` gives rows of the page's tables anchors `page--{id}` by the column headed so, the first such table
  wins; without `row`, `heading` and `item` place the id in the page as links do: `heading = "{id}"`.
- `check` reports `unresolved ref: doc:999` when the page, heading, item or row is missing; `url` refs go unchecked.
- A ref links its page for orphans, backlinks, reading order and previews: hovering one previews the row.
- `link` skips refs: a page aliased `doc` gets no link from `doc:245`.
- `mv` of a page a ref names rewrites `page` in the config; the LSP hovers and goes to refs as to links.

Done when `doc:245` in a vault like the health record links to its row of `generated/documents.md` in the HTML
and the LSP, `check` reports a ref to a missing row, and markdown output, Obsidian and GitHub show the text as is.

## HTML is a reading IDE

The one page HTML is a lightweight, fast IDE for humans reading a wiki that is the source others,
agents too, program in, commenting comes later. Everything below runs in the page, no build options.
