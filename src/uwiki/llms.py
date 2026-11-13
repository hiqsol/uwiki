"""Writes llms.txt (llmstxt.org): every page with its description, one section per folder."""

import os

from .order import Order
from .vault import read_description

class Llms:
    """Root pages first, then each folder's, depth first, all in reading order.

    Only pages of the selection are listed, summary defaults to the description of the folder page
    of the folder all given paths share.
    """

    def __init__(self, selection, output, title, summary=None):
        self.selection = selection
        self.scanner = selection.scanner
        self.outdir = os.path.dirname(os.path.abspath(output))
        self.title = title
        self.order = Order(self.scanner)
        top = selection.common
        if summary is None and top is not None and top.page and selection.selected(top):
            summary = read_description(top.file)
        self.summary = summary

    def text(self):
        lines = [f'# {self.title}', '']
        if self.summary:
            lines += [f'> {line}'.rstrip() for line in self.summary.strip().splitlines()] + ['']
        for folder in self.folders(self.scanner.root):
            lines += [f'## {self.heading(folder)}', '', *map(self.entry, self.pages(folder)), '']
        return '\n'.join(lines)

    def folders(self, folder):
        """Folders with pages, depth first."""
        if self.pages(folder):
            yield folder
        for child in self.order.children(folder):
            if child.is_folder:
                yield from self.folders(child)

    def heading(self, folder):
        """Title of the folder given paths share, path from it of the others: a folder given in a bigger vault
        reads as if it were the vault."""
        top = self.selection.common or self.scanner.root
        if folder is top:
            return folder.title if folder is self.scanner.root or folder.page else self.title
        return os.path.relpath(folder.fullpath, top.fullpath).replace(os.sep, '/') + '/'

    def pages(self, folder):
        selected = self.selection.selected
        pages = [child for child in self.order.children(folder) if not child.is_folder and selected(child)]
        return [folder, *pages] if selected(folder) else pages

    def entry(self, page):
        href = os.path.relpath(page.file, self.outdir).replace(os.sep, '/')
        description = read_description(page.file)
        return f'- [{page.title}]({href})' + (f': {description}' if description else '')
