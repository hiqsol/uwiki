# Backlog

Planned features in order of implementing, each with what makes it done.
Links resolve the same way in every command, new features reuse the vault resolver, not a copy of it.
Dependencies stay `markdown` only: watching, serving and previews use the standard library and plain JS.

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
