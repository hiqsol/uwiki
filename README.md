# uWiki -  micro wiki

Renders folder of markdown files to single HTML file.
With `--check-only` checks it instead: unresolved wiki links, missing images,
duplicate page names, frontmatter syntax and list numbering.
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

## Tests

```
python3 -m unittest discover tests
```
