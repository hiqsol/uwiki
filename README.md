# uWiki -  micro wiki

Renders folder of markdown files to single HTML file.
With `--check-only` checks it instead: unresolved wiki links and headings, missing images,
frontmatter syntax and list numbering, resolving links the same way rendering does.
I use it for Obsidian vaults.

## Installation

```
pip3 install -r requirements.txt
```

## Usage

```
./uwiki.py <folder> [title] [--html] [--md] [-o <output-dir>]
./uwiki.py --check-only <folder|file>...
```

Writes `<title>.html` and `<title>.md` (title defaults to folder name),
`--html` or `--md` to write only one of them.

Supported Obsidian syntax:

- `[[Page]]`, `[[Page|text]]`, `[[folder/Page]]`, `[[Page#Heading]]`, `[[#Heading]]`
- `![[Page]]`, `![[Page#Heading]]` embeds, `![[image.png]]`, `![[image.png|300]]`
- callouts `> [!note] Title`, foldable `> [!note]-`
- YAML front matter is stripped

Folder page is `index.md` or file named as folder, e.g. `Projects/Project.md`.

The HTML page is self-contained, light or dark by system preference:

- sidebar with collapsible contents following the page being read
- fuzzy full text search: press `/` or `Ctrl+K`, tolerates typos and abbreviations,
  `↑` `↓` `Enter` to open a result with matched words highlighted in text, `Esc` to clear

## Tests

```
python3 -m unittest discover tests
```
