"""Counts pages, words, headings, list items, links and orphan pages, finds largest pages."""

import os
import re
from pathlib import Path

from .convert import Converter
from .order import Links
from .vault import Filter, Vaults, read_parts

class Stats:
    """Statistics of markdown files grouped by folder or frontmatter key."""

    COLUMNS = ['pages', 'words', 'lines', 'headings', 'items', 'links', 'external', 'images']
    MDLINK = re.compile(r'(!?)\[[^\]]*\]\(([^)\s]+)[^)]*\)')
    ITEM = re.compile(r'^\s*(?:[-*+]|\d+[.)]|[a-z]\))\s')
    META = re.compile(r'^([\w-]+):[ \t]*(.*?)\s*$', re.MULTILINE)
    QUOTE = re.compile(r'^(?:[ \t]*>)+ ?')

    def __init__(self, paths, by='folder', include=(), exclude=()):
        self.vaults = Vaults(paths, Filter(include, exclude))
        self.by = by
        self.pages = []
        self.incoming = {}  # page file: links to it from counted pages
        self.links = {}  # scanner: links of its pages

    def collect(self):
        for scanner, page, shown in self.vaults.files():
            self.pages.append(self.count(scanner, page, shown))
            if scanner not in self.links:
                self.links[scanner] = Links(scanner)
            for target, _, _ in self.links[scanner].of(page):
                if target.source and target.source is not page.source:
                    self.incoming[target.source.fullpath] = self.incoming.get(target.source.fullpath, 0) + 1
        orphans = {page.source.fullpath for links in self.links.values() for page in links.orphans() if page.source}
        for page in self.pages:
            page['incoming'] = self.incoming.get(page['file'], 0)
            page['orphan'] = page['file'] in orphans
        return self

    def count(self, scanner, page, shown):
        source = page.source
        _, front, body, _ = read_parts(source.fullpath)
        meta = {k: v.strip('\'"') for k, v in self.META.findall(front)}
        res = dict.fromkeys(self.COLUMNS, 0)
        res.update(path=shown, file=source.fullpath, meta=meta, pages=1,
                   lines=len(body.splitlines()))
        for line in self.prose(body):
            res['words'] += len(line.split())
            res['headings'] += bool(Converter.HEADING.match(line))
            res['items'] += bool(self.ITEM.match(line))
            for embed, text in Converter.WIKILINK.findall(line):
                res['images' if embed and self.image(scanner, source, text) else 'links'] += 1
            for embed, url in self.MDLINK.findall(line):
                res['images' if embed else 'external' if '://' in url else 'links'] += 1
        return res

    @classmethod
    def prose(cls, body):
        """Lines outside code, quote marks and inline code left out."""
        for _, line in Converter.prose(body):
            yield Converter.CODE.sub('', cls.QUOTE.sub('', line))

    @classmethod
    def words(cls, body):
        return sum(len(line.split()) for line in cls.prose(body))

    @staticmethod
    def tokens(body):
        """Estimate of LLM tokens: 4 characters each."""
        return -(-len(body) // 4)

    @staticmethod
    def image(scanner, source, text):
        """Whether wiki link text names an image, not a page."""
        file = scanner.attachment(text.partition('|')[0].strip(), source.path)
        return (file is not None and Path(file).suffix.lower() in Converter.IMAGE_EXTS
                and not scanner.resolve(Converter.parse_target(text)[0], source.path))

    def group(self, page):
        if self.by == 'folder':
            return os.path.dirname(page['path']) or '.'
        return page['meta'].get(self.by) or '-'

    def groups(self):
        res = {}
        for page in self.pages:
            row = res.setdefault(self.group(page), dict.fromkeys(self.COLUMNS, 0))
            for col in self.COLUMNS:
                row[col] += page[col]
        return dict(sorted(res.items()))

    def total(self):
        return {col: sum(p[col] for p in self.pages) for col in self.COLUMNS}

    def largest(self, top):
        return sorted(self.pages, key=lambda p: -p['words'])[:top]

    def orphans(self):
        """Counted pages no chain of links leads to from the root folder page, as check --orphans finds them."""
        return sum(p['orphan'] for p in self.pages)

    def data(self, top):
        pages = [{k: v for k, v in p.items() if k != 'file'} for p in self.pages]
        return {
            'by': self.by,
            'groups': self.groups(),
            'total': self.total(),
            'largest': [p['path'] for p in self.largest(top)],
            'orphans': self.orphans(),
            'pages': pages,
        }

    def report(self, top):
        rows = [(name, row) for name, row in self.groups().items()] + [('total', self.total())]
        first = max(len(self.by), *(len(name) for name, _ in rows))
        widths = [max(len(col), *(len(str(row[col])) for _, row in rows)) for col in self.COLUMNS]
        line = lambda name, cells: '  '.join([name.ljust(first)] + [c.rjust(w) for c, w in zip(cells, widths)])
        lines = [line(self.by, self.COLUMNS)]
        lines += [line(name, [str(row[col]) for col in self.COLUMNS]) for name, row in rows]
        if top:
            lines += ['', 'largest:'] + [f"  {p['words']:>6}  {p['path']}" for p in self.largest(top)]
        orphans = self.orphans()
        if orphans:
            lines += ['', f'orphans: {orphans}, check --orphans lists them']
        return '\n'.join(lines)
