"""Writes llms.txt (llmstxt.org): every page with its description, one section per folder."""

import os

from .convert import Converter
from .vault import read_description

class LinkOrder(Converter):
    """Reads page like renderer does, notes pages its links lead to, in order."""

    def __init__(self, page, scanner):
        super().__init__(page, scanner)
        self.mode = 'md'
        self.targets = []

    def local_href(self, href):
        if self.is_local(href):
            self.note(self.resolve_href(href)[0])
        return super().local_href(href)

    def link(self, text):
        name = self.parse_link(text)[0]
        if name:
            self.note(self.scanner.resolve(name, self.source.path))
        return super().link(text)

    def note(self, target):
        if target is not None and target not in self.targets:
            self.targets.append(target)

class Llms:
    """Root pages first, then each folder's, folder page first, then pages in order it links them, then by name."""

    def __init__(self, scanner, output, title, summary=None):
        self.scanner = scanner
        self.outdir = os.path.dirname(os.path.abspath(output))
        self.title = title
        self.summary = summary if summary is not None else scanner.root.page and read_description(scanner.root.file)

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
        for child in folder.children.values():
            if child.is_folder:
                yield from self.folders(child)

    def heading(self, folder):
        if folder is self.scanner.root:
            return folder.title
        return os.path.relpath(folder.fullpath, self.scanner.path).replace(os.sep, '/') + '/'

    def pages(self, folder):
        pages = [child for child in folder.children.values() if not child.is_folder]
        if folder.page:
            order = LinkOrder(folder, self.scanner)
            order.read()
            linked = [page for page in order.targets if page in pages]
            pages = [folder, *linked, *(page for page in pages if page not in linked)]
        return pages

    def entry(self, page):
        href = os.path.relpath(page.file, self.outdir).replace(os.sep, '/')
        description = read_description(page.file)
        return f'- [{page.title}]({href})' + (f': {description}' if description else '')
