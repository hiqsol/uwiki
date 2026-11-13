"""References: record ids under configured prefixes, as `P:24`, `doc:245` or `HQD-640`, linked where they are
written as plain text, never rewritten.

```
[refs."P:"]                                    # defined in the vault: where **P:24** starts an item
[refs."HQD-"]
url = "https://jira.example.com/browse/HQD-{id}"   # where a ref the vault does not define leads
```

A ref is defined where it starts a heading, starts a list item or a table row in bold, or is a page's front matter
`id`: the bold that defines a term defines an id too. Its other occurrences link there, or to its `url` when the
vault defines none. A ref neither defined nor with a url is unresolved, one defined twice is ambiguous.

A letter after a ref and a space, then punctuation, is a point of it: `I:75 a.` defines point a of I:75,
`(I:75 a)` links there, else to I:75, which its first point defines when nothing else does.
"""

import os
import re
from dataclasses import dataclass

from .vault import front_matter_items, front_matter_tree, read_parts

@dataclass
class Definition:
    ref: str  # as written: P:24
    node: object  # page or folder it is in
    line: int  # source line number
    anchor: str  # anchor it links to: of the ref, of the page for a front matter id
    text: str  # what it defines, as plain text: P:24. Space type behaviors.
    done: bool = False  # a checked item: [x]

class Refs:
    # not after a word character nor one ids join with, so `a-HQD-1` and URLs keep theirs
    BEFORE = r'(?<![\w.:/-])'
    ID = r'\w(?:[\w.:-]*\w)?'
    POINT = r'(?: ([a-z])(?=[.,;:)*]|$))?'  # `I:75 a.`, `(I:75 a)`, not the article of `P:24 a deck`
    # links, code, tags and URLs keep refs in them as text
    SKIP = re.compile(r"""(`+).*?\1|!?\[\[.*?\]\]|!?\[[^\]]*\](?:\([^)]*\)|\[[^\]]*\])|<[^>]*>|\w+://\S+|www\.\S+""")
    FENCE = re.compile(r'^\s*(```|~~~)')
    # a heading starting with the ref, a list item or table row starting with it in bold, after quote marks
    DEFINITION = (r'^[ \t]*(?:>[ \t]?)*(?:#{1,6}[ \t]+(?:\*\*)?|(?:(?:[-*+]|\d+[.)])[ \t]+(?:\[(?P<x>[ xX])\][ \t]+)?'
                  r'|\|[ \t]*)\*\*)')
    EMPTY = None

    def __init__(self, table=None, path=None):
        table = table or {}
        if not isinstance(table, dict):
            raise ValueError(f'{path}: refs should be a table of prefixes')
        self.urls = {}  # prefix: url template or None
        for prefix, spec in table.items():
            if not prefix or re.match(r'\w', prefix[-1]):
                raise ValueError(f'{path}: refs."{prefix}": a prefix ends in its separator, as "P:" or "HQD-"')
            if not isinstance(spec, dict) or set(spec) - {'url'} or not isinstance(spec.get('url', ''), str):
                raise ValueError(f'{path}: refs."{prefix}" should be a table, with url = "...{{id}}" if any')
            url = spec.get('url')
            if url is not None and '{id}' not in url:
                raise ValueError(f'{path}: refs."{prefix}".url should have {{id}} in it')
            self.urls[prefix] = url
        alternatives = '|'.join(map(re.escape, sorted(self.urls, key=len, reverse=True)))
        self.pattern = re.compile(f'{self.BEFORE}({alternatives})({self.ID}){self.POINT}') if self.urls else None
        self.definition = re.compile(f'{self.DEFINITION}({alternatives})({self.ID}){self.POINT}(?![\\w:-])') \
            if self.urls else None
        self.full = re.compile(f'({alternatives})({self.ID})(?: ([a-z]))?') if self.urls else None
        self.quick = re.compile(alternatives) if self.urls else None  # most lines have no prefix at all
        self._definitions = None
        self._points = {}  # ref: its first point's definition
        self.scanner = None

    def __bool__(self):
        return bool(self.urls)

    @classmethod
    def of(cls, scanner):
        """Refs of the vault scanner scans, as its config gives them, read once."""
        refs = getattr(scanner, '_refs', None)
        if refs is None:
            from .config import Config, ConfigError
            config = Config.load(scanner.path)
            try:
                refs = cls(config.data.get('refs'), config.path)
            except ValueError as e:
                raise ConfigError(str(e)) from e
            refs.scanner = scanner
            scanner._refs = refs
        return refs

    def finditer(self, text):
        """Refs in text outside code, links, tags and URLs, as matches: [1] prefix, [2] id, [3] point or None,
        [0] the ref."""
        if self.pattern is None or not self.quick.search(text):
            return
        pos = 0
        for m in self.SKIP.finditer(text):
            yield from self.pattern.finditer(text, pos, m.start())
            pos = m.end()
        yield from self.pattern.finditer(text, pos)

    def sub(self, func, text):
        """Text with every ref func gives text for, as finditer finds them."""
        res, pos = '', 0
        for m in self.finditer(text):
            res += text[pos:m.start()] + func(m)
            pos = m.end()
        return res + text[pos:]

    def is_ref(self, value):
        """Whether value is a whole ref, as a front matter value is."""
        return bool(self.full and isinstance(value, str) and self.full.fullmatch(value.strip()))

    @staticmethod
    def anchor(ref):
        return 'ref-' + re.sub(r'[^0-9a-z]+', '-', ref.lower()).strip('-')

    def url(self, ref):
        """URL a ref leads to when the vault does not define it, None without one."""
        m = self.full.fullmatch(ref.split(' ')[0]) if self.full else None
        template = m and self.urls.get(m[1])
        return template.replace('{id}', m[2]) if template else None

    def resolve(self, ref):
        """Definition of the ref, the first one if several, of a point the ref's if the point has none,
        of a ref its first point's if the ref has none; None if none."""
        found = self.definitions.get(ref) or self.definitions.get(ref.split(' ')[0])
        return found[0] if found else self._points.get(ref.split(' ')[0])

    @property
    def definitions(self):
        """Ref: its definitions in the vault, by page path and line."""
        if self._definitions is None:
            self._definitions = {}
            if self and self.scanner is not None:
                for file, node in sorted(self.scanner.pages().items()):
                    for d in self.defined(node, file):
                        self._definitions.setdefault(d.ref, []).append(d)
                        if ' ' in d.ref:
                            self._points.setdefault(d.ref.split(' ')[0], d)
        return self._definitions

    def defined(self, node, file):
        """Definitions in the page file of node."""
        try:
            _, front, text, start = read_parts(file)
        except (OSError, UnicodeDecodeError):
            return []
        res = []
        for n, line in enumerate(front.splitlines()):
            if re.match(r'id:', line):
                for key, value in front_matter_items(front):
                    if key == 'id':
                        for v in value if isinstance(value, list) else [value]:
                            if self.is_ref(v):
                                res.append(Definition(v.strip(), node, n + 1, node.anchor, node.title))
                break
        fence = None
        for n, line in enumerate(text.splitlines(), start):
            f = self.FENCE.match(line)
            if fence:
                fence = None if f and line.lstrip().startswith(fence) else fence
                continue
            if f:
                fence = f[1]
                continue
            m = self.definition.match(line)
            if m:
                ref = m[2] + m[3] + (f' {m[4]}' if m[4] else '')
                rest = line[m.start(2):]
                bold = rest.split('**')[0] if line[:m.start(2)].rstrip().endswith('**') else ''
                # what the bold says, `**P:24. Space types.**`, else the whole line
                text = self.plain(bold if len(self.plain(bold)) > len(ref) + 2 else rest)
                res.append(Definition(ref, node, n, self.anchor(ref), text, (m['x'] or ' ') in 'xX'))
        return res

    @staticmethod
    def plain(text):
        """Line as plain text for a link title: markup dropped, links by their text, table cells joined."""
        text = re.sub(r'!?\[\[([^\]|]*\|)?([^\]]*)\]\]', r'\2', text)
        text = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', text)
        text = re.sub(r'[*_`]+', '', text)
        text = re.sub(r'\s*\|\s*', ' · ', text.strip().strip('|')).strip(' ·')
        return text if len(text) <= 160 else text[:159].rstrip() + '…'

    def front_refs(self, front):
        """(top level key, ref) for refs in front matter text values, nested ones too, `id` ones define."""
        if not self or not front or not self.quick.search(front):
            return []
        res = []
        def walk(key, value):
            if isinstance(value, dict):
                for v in value.values():
                    walk(key, v)
            elif isinstance(value, list):
                for v in value:
                    walk(key, v)
            elif isinstance(value, str):
                res.extend((key, m[0]) for m in self.finditer(value))
        for key, value in front_matter_tree(front).items():
            if key != 'id':
                walk(key, value)
        return res

    def duplicates(self, node):
        """(line, message) for refs node's page defines that are defined before, in it or another page."""
        res = []
        for ref, found in self.definitions.items():
            for d in found[1:]:
                if d.node is node:
                    first = found[0]
                    where = os.path.relpath(first.node.file, self.scanner.path).replace(os.sep, '/')
                    res.append((d.line, f'ref {ref} defined again, first at {where}:{first.line}'))
        return res
