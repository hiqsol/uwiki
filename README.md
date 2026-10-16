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
./uwiki.py <folder>
./uwiki.py --check-only <folder|file>...
```
