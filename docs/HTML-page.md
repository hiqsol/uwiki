# HTML page

`uwiki build` writes one self-contained file, light or dark by system preference, works from `file://`.

## Pages

- pages render as GitHub and Obsidian show them: CommonMark with tables, task lists and strikethrough;
  a page is laid out and drawn as it nears the window, so a long vault opens fast
- hover preview of a link target under the folders it is in, a page's with its metadata and front matter
  folded top right, links in it preview too, sidebar entries beside the sidebar
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
  on hover, tokens beside it on hover; bars from the right edge as `dust` draws them: the share of an entry
  over the lighter one of its branch; when filtering, shares are of pages found, beside counts of hits
- chips of `[schema]` values with page counts, a click adds or removes one
- pages, words and tokens shown out of all under the chips, after a triangle folding or unfolding the whole tree;
  a click on the count of problems shows only pages with problems

## Filter and go to

- `/` focuses the box filtering pages: words, `"exact text"`, `key:value` front matter, `in:folder`,
  `is:problem`, `-term`, e.g. `scope:core -status:stub deck`; `Enter` goes to the next match,
  the box goes to the URL as `?q=`, `×` or the `x` key clears it
- `Ctrl K` goes to a page or folder by letters of its name in order, e.g. `dkbld` for Deck Building:
  title matches first, then aliases, then paths; whole words and starts of words before scattered letters

## Keys and buttons

- `−` and `+` by the title or the `-` and `+` keys make the text of pages and previews smaller or larger,
  the line buttons beside them or the `<` and `>` keys put their lines closer or wider apart,
  `0` restores both, remembered per browser
- `j` and `k` go to the next and previous page, `t` to the top, `[` and `]` fold and unfold the whole tree
- `u` and the logo before the title go to the page `build --up URL` gives, as a site index
- `?` by the title or the `?` key opens help: what the page is, uWiki version, build time and the git
  commit built from, keys, search terms and mouse gestures; under `serve` whether the server answers;
  its config link shows build options and the vault config file as they were
