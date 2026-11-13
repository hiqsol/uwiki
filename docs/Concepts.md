# Concepts

## Vault

Folder of markdown pages, rooted at the nearest folder with `.obsidian` or `uwiki.toml`,
else the one given paths share, so a file given alone links in the whole vault.
Commands take its folders and files, skipping hidden ones, `node_modules` and `vendor`,
`--exclude GLOB` skips more, `--include GLOB` takes back, globs as in `.gitignore`,
`{a,b}` matching either, from the vault root, ones of the [config](Config.md) from its folder.
A file named outright is taken even if hidden, not if excluded. `uwiki ls` lists the files commands take.

## Folder page

`README.md`, `index.md` or page named as its folder, the contents of the folder.

## Title

Title of a page: front matter `title`, else the heading it starts with, else its name;
`AGENTS.md` is always titled `AGENTS.md`, the name tools look for.

## Reading order

Order of `build`, `llms` and the HTML sidebar: folder page, then pages in the order it links them,
every other page right after the first page linking it, unlinked ones last.

## Links

Links resolve the same way in every command, [refs](#refs) too:

- `[[Page]]` by name, then by front matter `aliases`, nearest first; `[[Page|text]]`, `[[folder/Page]]`
- `[[Page#Heading]]`, `[[Page#3]]` item 3 of the first numbered list of Page, `[[Page#Heading#3]]` under Heading
- `[text](../Page.md#heading)` by path relative to the page, heading by its GitHub anchor
- embeds `![[Page]]`, `![[Page#Heading]]`, `![[image.png|300]]`, callouts `> [!note] Title`

## Links, mentions and refs

What points somewhere is a link once rendered; the source says how explicitly:

- a **link** is written as one, `[[Page]]` or `[text](Page.md)`, two syntaxes of one thing
- a **mention** is a page title or alias in plain text, fuzzy: plurals, any case, a term two pages share;
  `check --mentions` warns about it and `link` rewrites it into a link once, a human deciding where it leads
- a **ref** is a record id in plain text under a configured prefix, `P:24`, `doc:245`, `HQD-640`, exact:
  linked at every render, never rewritten, as the text is a value the database, tracker and agents share too

Ambiguous text is decided once and written into the source, exact text is resolved every time it renders.

## Refs

`[refs]` of the [config](Config.md#refs) names prefixes, the separator ending them: `P:`, `doc:`, `HQD-`.
A ref is a prefix not after a word character, then an id of word characters, `.`, `-` and `:`
ending in a word character: `ai:claude-code:1a2b` is id `claude-code:1a2b` when `ai:` is a prefix.
Only configured prefixes match, so COVID-19 stays text; none match in code, links and URLs,
a code span keeps a ref as text.

A ref is defined where it starts a heading, starts a list item or a table row in bold,
as the bold that defines a term does, or is a page's front matter `id`:

```markdown
- [ ] **P:24. Space types.** No dice: every effect is fixed.
| **doc:245** | Blood test | 2026-03-01 |
```

Every other occurrence links to its definition, else to the `url` its prefix gives;
`check` reports a ref neither defined nor with a url, and one defined twice.
A ref of a checked item `[x]` is done, struck through where it links.
Refs link pages for backlinks, orphans and reading order, in front matter values too;
markdown output, Obsidian and GitHub show them as written, `ls --refs` lists where they are defined.

## Orphan

Page no chain of links leads to from the root folder page, `check --orphans` reports them.
