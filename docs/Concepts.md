# Concepts

## Vault

Folder of markdown pages, rooted at the nearest folder with `.obsidian`, else the one given paths share.
Commands take its folders and files, skipping hidden ones, `node_modules` and `vendor`,
`--exclude GLOB` skips more, `--include GLOB` takes back, globs as in `.gitignore`,
`{a,b}` matching either. `uwiki ls` lists the files commands take.

## Folder page

`README.md`, `index.md` or page named as its folder, the contents of the folder.

## Title

Title of a page: front matter `title`, else the heading it starts with, else its name;
`AGENTS.md` is always titled `AGENTS.md`, the name tools look for.

## Reading order

Order of `build`, `llms` and the HTML sidebar: folder page, then pages in the order it links them,
every other page right after the first page linking it, unlinked ones last.

## Links

Links resolve the same way in every command:

- `[[Page]]` by name, then by front matter `aliases`, nearest first; `[[Page|text]]`, `[[folder/Page]]`
- `[[Page#Heading]]`, `[[Page#3]]` item 3 of the first numbered list of Page, `[[Page#Heading#3]]` under Heading
- `[text](../Page.md#heading)` by path relative to the page, heading by its GitHub anchor
- embeds `![[Page]]`, `![[Page#Heading]]`, `![[image.png|300]]`, callouts `> [!note] Title`

## Orphan

Page no chain of links leads to from the root folder page, `check --orphans` reports them.
