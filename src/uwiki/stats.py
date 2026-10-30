"""Counts pages, words, headings, list items and links, finds largest and orphan pages."""

import os
import re
from pathlib import Path

from .convert import Converter
from .vault import Filter, Vaults

class Stats:
    """Statistics of markdown files grouped by folder or frontmatter key."""

    COLUMNS = ['pages', 'words', 'lines', 'headings', 'items', 'links', 'external', 'images']
    WIKILINK = re.compile(r'(!?)\[\[(.+?)\]\]')
    MDLINK = re.compile(r'(!?)\[[^\]]*\]\(([^)\s]+)[^)]*\)')
    ITEM = re.compile(r'^\s*(?:[-*+]|\d+[.)]|[a-z]\))\s')
    META = re.compile(r'^([\w-]+):[ \t]*(.*?)\s*$', re.MULTILINE)
    QUOTE = re.compile(r'^(?:[ \t]*>)+ ?')

    def __init__(self, paths, by='folder', include=(), exclude=()):
        self.vaults = Vaults(paths, Filter(include, exclude))
        self.by = by
        self.pages = []
        self.incoming = {}

    def collect(self):
        for scanner, page, shown in self.vaults.files():
            self.pages.append(self.count(scanner, page, shown))
        for page in self.pages:
            page['incoming'] = self.incoming.get(page['file'], 0)
        return self

    def count(self, scanner, page, shown):
        source = page.page if page.is_folder else page
        with open(source.fullpath, encoding='utf-8') as f:
            text = f.read()
        m = Converter.FRONT_MATTER.match(text)
        meta = {k: v.strip('\'"') for k, v in self.META.findall(m[0])} if m else {}
        body = text[m.end():] if m else text
        res = dict.fromkeys(self.COLUMNS, 0)
        res.update(path=shown, file=source.fullpath, meta=meta, pages=1,
                   lines=len(body.splitlines()), is_index=page.is_folder)
        for line in Converter.prose(body):
            line = Converter.CODE.sub('', self.QUOTE.sub('', line))
            res['words'] += len(line.split())
            res['headings'] += bool(Converter.HEADING.match(line))
            res['items'] += bool(self.ITEM.match(line))
            for embed, target in self.WIKILINK.findall(line):
                self.wikilink(scanner, source, embed, target, res)
            for embed, url in self.MDLINK.findall(line):
                res['images' if embed else 'external' if '://' in url else 'links'] += 1
        return res

    def wikilink(self, scanner, source, embed, text, res):
        name = Converter.parse_link(text)[0]
        file = scanner.attachment(text.partition('|')[0].strip(), source.path)
        if file and not scanner.resolve(name, source.path):
            image = Path(file).suffix.lower() in Converter.IMAGE_EXTS
            res['images' if embed and image else 'links'] += 1
            return
        res['links'] += 1
        target = scanner.resolve(name, source.path) if name else None
        node = target.page if target and target.is_folder else target
        if node and node.fullpath != source.fullpath:
            self.incoming[node.fullpath] = self.incoming.get(node.fullpath, 0) + 1

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
        """Pages not linked from the counted ones, folder pages excepted."""
        return [p for p in self.pages if not p['incoming'] and not p['is_index']]

    def data(self, top):
        pages = [{k: v for k, v in p.items() if k not in ('file', 'is_index')} for p in self.pages]
        return {
            'by': self.by,
            'groups': self.groups(),
            'total': self.total(),
            'largest': [p['path'] for p in self.largest(top)],
            'orphans': [p['path'] for p in self.orphans()],
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
            lines += ['', 'orphans:'] + [f"  {p['path']}" for p in orphans]
        return '\n'.join(lines)
