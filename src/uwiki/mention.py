"""Plain text mentions of page titles and aliases, as `check --mentions` warns about them and `link` links them."""

import os
import re
from dataclasses import dataclass

from .config import Config
from .convert import Converter
from .index import Index
from .order import Links
from .refs import Refs
from .vault import read_aliases
from .wrap import WIDTH, rewrap


@dataclass
class Mention:
    line: int  # index in the file
    start: int
    end: int
    text: str
    node: object
    term: str  # title or alias it mentions, singular
    name: str  # page name or alias a link to it takes
    own: bool = False  # of the page it is in


class Mentions:
    """Titles and aliases as whole words, plurals too, with the first letter as written and the rest in any case,
    outside code, headings, links, bold definitions and generated blocks `index` fills from front matter;
    terms naming two pages are left out."""

    SKIP = re.compile(r"""(`+).*?\1|!?\[\[.*?\]\]|!?\[[^\]]*\](?:\([^)]*\)|\[[^\]]*\])|<[^>]*>|https?://\S+"""
                      r"""|\*\*[^*\n]+?\*\*""")

    def __init__(self, scanner, ignore=(), min_length=3, ignore_case=False):
        self.scanner = scanner
        self.refs = Refs.of(scanner)
        self.ignore_case = ignore_case
        ignored = {term.lower() for term in ignore}  # in any case, as terms match: CLAUDE.md is no Claude
        exact, plural = {}, {}  # term in lower case: (node, term as written, name a link takes)
        for node in scanner.pages().values():
            if node is scanner.root and not node.page:
                continue
            # folder page Card.md of Cards/ goes by its own title, README.md and index.md by the folder's
            named = node.page if node.is_folder and node.page.name.lower() not in ('index', 'readme') else node
            for term, name in [(named.title, named.name), *((a, a) for a in read_aliases(node.file))]:
                term = term.strip()
                if len(term) < min_length or term.lower() in ignored:
                    continue
                self.add(exact, term, (node, term, name))
                for form in self.plurals(term):
                    self.add(plural, form, (node, term, name))
        self.terms = {k: v for k, v in {**plural, **exact}.items() if v is not None}
        # an ignored name that is no term, e.g. a game title Star Realms, keeps the terms in it unlinked
        self.terms.update({term.lower(): None for term in ignore if term.lower() not in self.terms})
        self.pattern = re.compile(r'(?<!\w)' + self.trie(self.terms) + r'(?!\w)', re.IGNORECASE) \
            if self.terms else None

    @staticmethod
    def add(terms, form, value):
        """Term form naming the page, None for one naming two."""
        key = form.lower()
        if key in terms and (terms[key] is None or terms[key][0] is not value[0]):
            terms[key] = None
        else:
            terms.setdefault(key, value)

    @staticmethod
    def plurals(term):
        res = [term + 's', term + 'es']
        if term.endswith('y'):
            res.append(term[:-1] + 'ies')
        return res

    @classmethod
    def trie(cls, words):
        """Regex of words sharing their prefixes, longest first: fast with thousands of them."""
        tree = {}
        for word in words:
            node = tree
            for c in word:
                node = node.setdefault(c, {})
            node[''] = {}
        def pattern(node):
            alts = [re.escape(c) + pattern(sub) for c, sub in node.items() if c]
            if not alts:
                return ''
            res = alts[0] if len(alts) == 1 else '(?:' + '|'.join(alts) + ')'
            return f'(?:{res})?' if '' in node else res
        return pattern(tree)

    def find(self, page, own=False):
        """Mentions in page of other pages, in text order, with own also of the page itself."""
        if self.pattern is None or page.source is None:
            return
        try:
            text, start = Converter.read_text(page.source)
        except ValueError:
            return
        for n, line, spill in self.lines(text):
            for m in self.pattern.finditer(line):
                if self.terms[m[0].lower()] is None or m.start() < spill:
                    continue
                node, term, name = self.terms[m[0].lower()]
                if node is page and not own or not (self.ignore_case or m[0][0] == term[0]):
                    continue
                yield Mention(start - 1 + n, m.start(), m.end(), m[0], node, term, name, node is page)

    def unlinked(self, page, links, every=False, own=False):
        """Mentions to link: the first one of each page the page does not link yet, by name or path, or every one
        with every; with own also mentions of the page itself."""
        linked, seen = set() if every else set(links.targets(page)), set()
        for mention in self.find(page, own):
            if not mention.own:
                if mention.node in linked or mention.node in seen:
                    continue
                if not every:
                    seen.add(mention.node)
            yield mention

    def lines(self, text):
        """Line indexes and prose lines with code, links and bold blanked, and how much of each an ignored name
        wrapped from the line before covers: `Star` of `Twilight\\nStar`, `Imperium` of `Twilight\\nImperium`
        are no mentions."""
        res, bold, generated = [], False, False  # bold wrapped from the line before, inside a generated block
        for n, line in Converter.prose(text):
            if line.lstrip().startswith(Index.OPENING):
                generated = True
            if generated:
                generated = Index.CLOSING not in line
                res.append((n, ''))
                continue
            if Converter.HEADING.match(line) or Converter.LINK_DEF.match(line) or not line.strip():
                bold = False
                res.append((n, ''))
                continue
            if bold:
                end = line.find('**')
                if end < 0:
                    res.append((n, ''))
                    continue
                line, bold = ' ' * (end + 2) + line[end + 2:], False
            line = self.SKIP.sub(lambda m: ' ' * len(m[0]), line)
            line = self.refs.sub(lambda m: ' ' * len(m[0]), line)  # a page aliased `doc` gets no link from doc:245
            if '**' in line:
                line, bold = line[:line.index('**')], True
            res.append((n, line))
        spill = 0
        for i, (n, line) in enumerate(res):
            after = res[i + 1][1] if i + 1 < len(res) and res[i + 1][0] == n + 1 else ''
            indent = len(after) - len(after.lstrip())
            joined = line.rstrip() + ' ' + after.lstrip()
            ends, wrapped = len(line.rstrip()), 0
            for m in self.pattern.finditer(joined):
                if m.start() < ends < m.end() and self.terms[m[0].lower()] is None:
                    line = line[:m.start()] + ' ' * (len(line) - m.start())
                    wrapped = indent + m.end() - ends - 1
            yield n, line, spill
            spill = wrapped

    def link(self, mention, source, table=False):
        """Wiki link a mention becomes: `[[Star]]`, `[[Star]]s`, `[[ForceDiscard|Force discard]]`,
        `[[Warp orbit]]` for alias `Warp Orbit` as names match in any case; a table cell escapes the pipe."""
        name = mention.name
        if self.scanner.resolve(name, source.path) is not mention.node:
            name = mention.node.path.strip('/')
        text = mention.text
        for suffix in ('', 's', 'es'):
            base = text[:len(text) - len(suffix)]
            if text.endswith(suffix) and base.lower() == name.lower() \
                    and (base == name or self.scanner.resolve(base, source.path) is mention.node):
                return f'[[{base}]]{suffix}'
        return f'[[{name}\\|{text}]]' if table else f'[[{name}|{text}]]'


def link_mentions(vaults, ignore=(), min_length=3, ignore_case=False, self_bold=False, width=WIDTH, dry_run=False,
                  exclude=(), every=False):
    """Links plain mentions in pages of vaults but those an exclude glob from the config folder matches: the first one
    of each page a page does not link yet, every one with every, as check warns about them; with self_bold makes
    mentions of the page itself bold, rewraps lines longer than width, yields path shown and its changed lines as
    (line number, old, new); dry run writes nothing."""
    mentions, configs, links = {}, {}, {}
    for scanner, page, shown in vaults.files():
        if scanner not in mentions:
            mentions[scanner] = Mentions(scanner, ignore, min_length, ignore_case)
            configs[scanner] = Config.load(scanner.path)
            links[scanner] = Links(scanner)
        if page.source is None:
            continue
        path = os.path.relpath(page.source.fullpath, scanner.path).replace(os.sep, '/')
        if configs[scanner].matches(path, exclude):
            continue
        found = list(mentions[scanner].unlinked(page, links[scanner], every, own=self_bold))
        if not found:
            continue
        with open(page.source.fullpath, encoding='utf-8') as f:
            text = f.read()
        lines = text.split('\n')
        old = list(lines)
        for mention in reversed(found):
            line = lines[mention.line]
            if mention.own:
                link = f'**{mention.text}**'
            else:
                link = mentions[scanner].link(mention, page, table=line.lstrip().startswith('|'))
            lines[mention.line] = line[:mention.start] + link + line[mention.end:]
        if lines == old:
            continue
        new = rewrap('\n'.join(lines), width)[0]
        if not dry_run:
            with open(page.source.fullpath, 'w', encoding='utf-8') as f:
                f.write(new)
        yield shown, [(n + 1, a, b) for n, (a, b) in enumerate(zip(old, lines)) if a != b]
