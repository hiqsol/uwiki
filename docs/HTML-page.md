# HTML page

`uwiki build` writes one self-contained file, light or dark by system preference, works from `file://`.

## Pages

- pages render as GitHub and Obsidian show them: CommonMark with tables, task lists and strikethrough;
  a page is laid out and drawn as it nears the window, so a long vault opens fast
- hover preview of a link target under the folders it is in, a page's with its metadata and front matter
  folded top right of its header, links in it preview too, sidebar entries beside the sidebar
- [refs](Concepts.md#refs) link where they are defined, titled with what they define, a done one struck through,
  in front matter too, previewing the item, row or section defining them; a click on a definition copies its link
- metadata and front matter top right of page header, problems marked at their lines;
  metadata folds to problems, tokens, backlinks and file name, unfolds to what `check` reports, words, tokens
  and reading time, backlinks, file name and folder; file name and folder only where title and folders
  don't tell them; nested front matter keys beside the key above them in the same table
- tokens estimated as 4 bytes of UTF-8 each, so text in other scripts than Latin counts more
- code blocks highlighted by Prism and `mermaid` blocks drawn as they near the window, the libraries
  loaded from CDNs on first need; offline, code stays plain

## Sidebar

- contents following the page being read, its edge drags its width,
  a click on a branch title folds or unfolds it too; guide lines show nesting, the one of the page
  being read stands out
- share of tokens of a branch with all pages under it right of its title, of a page
  over 5% too, of other pages on hover, tokens beside it on hover; bars from the right edge as `dust` draws them: the share of an entry
  over the lighter one of its branch; when filtering, shares are of pages found, beside counts of hits
- `[schema]` keys over the contents in a tree like it, folded at first, unfolded ones remembered per browser:
  values under their key, ones nested with slashes, as `tech/action`, under their group; a value has the number and
  the share of tokens of the pages it finds with the other terms of the search; a click on its box, or name if no group, adds it to the search,
  the box of a key pages having it, `key:*`,
  a Shift or right click takes it out, a second one drops it; values under a key or group added or taken out show it dimmed,
  a click on one added so takes it out; a folded key tells its terms; facets and contents scroll as one
- bands across the sidebar head both trees, their triangles standing out left of the toggles:
  the one of facets counts pages with front matter and with each key, e.g. `73 frontmatters: 73 scope · 14 rollout`,
  found of all when filtering, folds the facets into it, remembered per browser, folded it tells their terms;
  the one of the contents sticks at the top, its triangle folds or unfolds the whole tree,
  then pages, words and tokens shown out of all;
  a click on the count of problems shows only pages with problems

## Filter and go to

- `/` focuses the box filtering pages: words, `"exact text"`, `key:value` front matter, `in:folder`,
  `is:problem`, `-term`, e.g. `scope:core -status:stub deck`; `tags:tech` finds `tech/action` too, `key:*` any value; `Enter` goes to the next match,
  the box goes to the URL as `?q=`, `×` or the `x` key clears it
- `Ctrl K` goes to a page or folder by letters of its name in order, e.g. `dkbld` for Deck Building:
  title matches first, then aliases, then paths; whole words and starts of words before scattered letters

## Keys and buttons

Keys go by what they type in Latin layouts, Dvorak too, and by where they are on the keyboard in others,
as `Ctrl Л` for `Ctrl K` in a Cyrillic one.

- `−` and `+` by the title or the `-` and `+` keys make the text of pages and previews smaller or larger,
  the line buttons beside them or the `<` and `>` keys put their lines closer or wider apart,
  `0` restores both, remembered per browser
- `j` and `k` go to the next and previous page, `t` to the top, `[` and `]` fold and unfold the whole tree
- `u` and the logo before the title go to the page `build --up URL` gives, as a site index
- `?` by the title or the `?` key opens help: what the page is, uWiki version, build time and the git
  commit built from, keys, search terms and mouse gestures; under `serve` and `--live` whether the server answers;
  its config link shows build options and the vault config file as they were
