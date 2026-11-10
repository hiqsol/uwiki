# Commands

```
uwiki build  <paths> [-o OUTPUT] [--title TITLE] [--html | --md] [--no-backlinks] [--no-front-matter] [--up URL]
uwiki watch  <paths> [build options] [-q] [--interval 0.5]
uwiki serve  <paths> [watch options] [-p 8000] [--host 127.0.0.1] [--open]
uwiki check  <paths> [--orphans] [--unlisted] [--mentions] [--mentions-exclude GLOB] [--no-folder-links] [--max-lines N]
uwiki link   <paths> [--dry-run] [-w 70]
uwiki llms   <paths> [-o FILE] [--title TITLE] [--check]
uwiki index  <paths> [--check]
uwiki ls     <paths> [--external] [-z]
uwiki stats  <paths> [--by folder|KEY] [--top N] [--json]
uwiki wrap   <paths> [-w 70] [--check]
uwiki mv     <from> <to> [--dry-run]
uwiki lsp
```

`uwiki <command> --help` lists all options, [Config](Config.md) gives them defaults.
Paths are folders and files of a [vault](Concepts.md#vault).

## build

Writes `<name>.html` and `<name>.md`, named by `--title` or the folder, `-o out/Wiki.html` only one;
the wiki is titled as its index page is (`README.md`, `index.md`), unless `--title` is given;
a page shows its folders, metadata and front matter; a link to a page left out fails the build;
`--up ./` links the logo before the title, and the `u` key, to the index of a site of several wikis.
[HTML page](HTML-page.md) tells what the HTML does.

## watch and serve

`watch` builds again on change of a page, attachment or the config, `serve` also serves the HTML
on `http://127.0.0.1:8000`, reloading the page, its blocks with `data-line` of the source line they start at;
both restart on change of uwiki's own code, as on upgrade, unless it fails to import,
and of options the config gives them.

## check

Reports unresolved links, headings and items, missing images, front matter out of `[schema]`
and list numbering as `path:line: message`, exits 1 if any:

- `--orphans` reports [orphans](Concepts.md#orphan)
- `--unlisted` and `--mentions` warn about pages their folder page does not link
  and plain text mentions of page titles, outside `index` blocks and pages `--mentions-exclude` matches
- `--max-lines` reports longer pages
- `--acyclic KEY` reports pages a chain of pages that front matter key names leads back to,
  `[check] inverse` page valued keys that do not name each other back
- `--stale-days N` warns about pages whose latest `--stale-date KEY` is older,
  `--stale-until KEY` about pages whose date in that key has come
- `[check.code-paths]` reports code spans ending in `.md` or holding a `/` in matching pages
  that name no file or folder in the folder it gives
- `[check] layers` makes a page link only to pages of its layer or earlier ones, see [Config](Config.md)

## link

Links the plain text mentions `check --mentions-every` warns about: `[[Star]]s`.

## llms

Writes [llms.txt](https://llmstxt.org): a section per folder of `- [title](path): description`.

## index

Fills `<!-- generated: NAME -->` ... `<!-- /generated -->` blocks of pages
with the other pages of their folder, `- [title](path): description` each,
keeping their order and the lines linking subfolders, `--check` reports blocks out of date;
`[index.NAME]` of the [config](Config.md) changes lines, order and what is left out.

## ls

Lists the files commands take, `--external` external links, for other tools:
`uwiki ls -z docs | xargs -0 typos`, `uwiki ls --external docs | lychee -`.

## stats

Counts pages, words, lines, headings, items, links and images by folder or front matter key.

## wrap

Rewraps paragraphs and list items longer than `-w 70`, `--check` reports them.

## mv

Moves a page, folder or attachment rewriting every link to it, with `git mv` in a git work tree.

## lsp

Language server for editors, see [Editors](Editors.md).
