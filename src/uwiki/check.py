"""Checks vault the way it builds: links, headings, images, frontmatter, list numbering, orphans."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from .config import Config
from .convert import Converter
from .order import Links
from .vault import Filter, Scanner, Vaults, front_matter_items, read_aliases, read_parts

@dataclass
class CheckOptions:
    folder_links: bool = True
    orphans: bool = False
    unlinked: bool = False
    unlisted: bool = False
    mentions: bool = False
    mentions_ignore: tuple = ()
    mentions_min_length: int = 3
    mentions_ignore_case: bool = False

class CheckConverter(Converter):
    """Converts page like renderer does, reports what would render broken."""

    IMAGE = re.compile(r'!\[[^\]]*\]\(([^)\s]+)\)')
    NUMBERED = re.compile(r'^([ \t]*)(\d+)\. ')

    def __init__(self, page, scanner, report, options):
        super().__init__(page, scanner)
        self.report = report
        self.options = options
        self.mode = 'md'
        self.lists = []  # [indent, last number] of open numbered lists, outermost first
        self.blank = False

    def process_line(self, line):
        for n, raw in enumerate(line.splitlines(keepends=True)):
            self.check_numbering(raw, self.line + n)
        return super().process_line(line)

    def process_links(self, text):
        res = super().process_links(text)
        for src in self.IMAGE.findall(text):
            if '://' not in src and not (Path(self.source.fullpath).parent / src).exists():
                self.report(self.line, f'missing image: {src}')
        return res

    def markdown_link(self, match):
        if not match[1]:
            self.check_href(match[3], self.line + match.string.count('\n', 0, match.start()))
        return super().markdown_link(match)

    def link_definition(self, match):
        self.check_href(match[1].strip('<>'), self.line)
        return super().link_definition(match)

    def check_href(self, href, line):
        """Relative link names existing file inside vault, as spelled, page link also its heading."""
        path, _, fragment = unquote(href).partition('#')
        if ':' in path or path.startswith('//'):
            return
        if path.startswith('/'):
            return self.report(line, f'absolute link: {href}')
        if Scanner.vault_path(path, self.source.path) is None:
            return self.report(line, f'link leaves vault: {href}')
        target, heading = self.resolve_href(href)
        if target is not None and self.ITEM.fullmatch(fragment):
            node = target.source
            heading = True
            if node is None or not self.find_item(node, '', fragment):
                self.report(line, f'missing item: {href}')
        file = os.path.join(os.path.dirname(self.source.fullpath), path)
        if path and not os.path.exists(file):
            return self.report(line, f'link differs from file name: {href}' if target else f'unresolved link: {href}')
        if target is None and path.lower().endswith('.md'):
            return self.report(line, f'unresolved link: {href}')
        if path and os.path.isdir(file) and not self.options.folder_links:
            self.report(line, f'folder link: {href}')
        elif target is not None and heading is None:
            self.report(line, f'missing heading: {href}')

    def link(self, text, checked=False):
        self.check_link(text)
        return super().link(text, checked)

    def embed_note(self, text):
        self.check_link(text)
        return ''

    def check_link(self, text):
        name, heading, item, _ = self.parse_target(text)
        target = self.scanner.resolve(name, self.source.path) if name else self.source
        if target is None:
            if heading or item or not self.attachment(text):
                self.report(self.line, f'unresolved link: [[{name}]]')
            return
        node = target.source
        if heading and not heading.startswith('^'):
            if node is None or not self.section(self.read_text(node)[0], heading):
                return self.report(self.line, f'missing heading: [[{name}#{heading}]]')
        if item and (node is None or not self.find_item(node, self.title_section(target, heading), item)):
            self.report(self.line, f'missing item: [[{text.partition("|")[0].strip()}]]')

    def check_numbering(self, line, lineno):
        """Numbered lists count from 1, nesting by indentation, lazy continuation lines keep list going."""
        m = self.NUMBERED.match(line)
        if not m:
            if line.strip() and not line[0].isspace() and (self.blank or self.LIST_BREAK.match(line)):
                self.lists = []
            self.blank = not line.strip()
            return
        self.blank = False
        indent, num = len(m[1].expandtabs(4)), int(m[2])
        while self.lists and self.lists[-1][0] > indent:
            self.lists.pop()
        if not self.lists or self.lists[-1][0] < indent:
            self.lists.append([indent, 0])
        expected = self.lists[-1][1] + 1
        if num != expected:
            self.report(lineno, f'list number {num}, expected {expected}')
        self.lists[-1][1] = num

class Checker:
    """Checks vault consistency the way builder sees it, reports problems as `path:line: message`."""

    FRONT_MATTER_START = re.compile(r'\A---[ \t]*\r?\n')

    def __init__(self, paths, include=(), exclude=(), options=None):
        self.vaults = Vaults(paths, Filter(include, exclude))
        self.options = options or CheckOptions()
        self.problems = []
        self.warnings = []
        self.links = {}  # scanner: links of its pages
        self.checked = {}  # checked page: (scanner, path to show)
        self.schemas = {}  # scanner: front matter schema of its vault config

    def check(self):
        for scanner, page, shown in self.vaults.files():
            self.checked[page] = scanner, shown
            self.check_file(scanner, page, shown)
        if self.options.orphans or self.options.unlinked:
            self.check_orphans()
        if self.options.unlisted:
            self.check_unlisted()
        if self.options.mentions:
            self.check_mentions()
        return self.problems

    PLAIN_SKIP = re.compile(r"""(`+).*?\1|!?\[\[.*?\]\]|!?\[[^\]]*\](?:\([^)]*\)|\[[^\]]*\])|<[^>]*>|https?://\S+""")

    def check_mentions(self):
        """Warns about the first plain text mention of another page title or alias, page not linking it."""
        terms = {}
        for page, (scanner, shown) in self.checked.items():
            if scanner not in terms:
                terms[scanner] = self.mention_terms(scanner)
            pattern, nodes = terms[scanner]
            if pattern is None:
                continue
            source = page.source
            try:
                text, start = Converter.read_text(source)
            except ValueError:
                continue
            linked = self.targets(scanner, page)
            seen = set()
            for n, line in Converter.prose(text):
                if Converter.HEADING.match(line) or Converter.LINK_DEF.match(line):
                    continue
                for m in pattern.finditer(self.PLAIN_SKIP.sub(lambda m: ' ' * len(m[0]), line)):
                    key = m[0].lower() if self.options.mentions_ignore_case else m[0]
                    node = nodes.get(key)
                    if node is None or node is page or node in linked or node in seen:
                        continue
                    seen.add(node)
                    self.warnings.append(f'{shown}:{start + n}: warning: unlinked mention: {m[0]}')

    def mention_terms(self, scanner):
        """Regex of page titles and aliases as whole words, and the page each names; ones naming two pages left out."""
        case = self.options.mentions_ignore_case
        norm = lambda term: term.lower() if case else term
        ignore = {norm(term) for term in self.options.mentions_ignore}
        nodes, shared = {}, set()
        for node in scanner.pages().values():
            if node is scanner.root and not node.page:
                continue
            for term in [node.title, *read_aliases(node.file)]:
                term = term.strip()
                key = norm(term)
                if len(term) < self.options.mentions_min_length or key in ignore:
                    continue
                if nodes.get(key, node) is not node:
                    shared.add(key)
                nodes[key] = node
        for key in shared:
            del nodes[key]
        if not nodes:
            return None, nodes
        pattern = re.compile(r'(?<!\w)' + self.trie(nodes) + r'(?!\w)', re.IGNORECASE if case else 0)
        return pattern, nodes

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

    def check_unlisted(self):
        """Warns about pages and folders their folder page does not link, as contents should."""
        for page, (scanner, shown) in self.checked.items():
            folder = page.folder
            if folder is None or folder.page is None or page is scanner.root:
                continue
            if page not in self.targets(scanner, folder):
                self.warnings.append(f'{shown}:1: warning: not listed in {folder.page.name}.md')

    def targets(self, scanner, page):
        """Pages and folders page links to, as build and its reading order see them."""
        if scanner not in self.links:
            self.links[scanner] = Links(scanner)
        return self.links[scanner].targets(page)

    def check_orphans(self):
        """Pages links from root folder page do not lead to, pages no other page links, warnings for the latter."""
        vaults = {}
        for page, (scanner, shown) in self.checked.items():
            if scanner not in vaults:
                vaults[scanner] = self.vault_links(scanner)
            pages, linked, reached = vaults[scanner]
            if page not in pages or page is scanner.root:
                continue
            if self.options.orphans and page not in reached:
                reason = f'not reachable from {scanner.root.page.name}.md' if page in linked else 'no page links here'
                self.problems.append(f'{shown}:1: orphan page: {reason}')
            elif self.options.unlinked and page not in linked:
                self.warnings.append(f'{shown}:1: warning: no page links here')

    def vault_links(self, scanner):
        """Vault pages, ones other pages link to, ones links from root folder page lead to, all pages read."""
        pages = set(scanner.pages().values())
        linked = {target for page in pages for target in self.targets(scanner, page) if target is not page}
        return pages, linked, self.links[scanner].reach() if scanner.root.page else linked

    def schema(self, scanner):
        if scanner not in self.schemas:
            self.schemas[scanner] = Config.load(scanner.path).schema
        return self.schemas[scanner]

    def check_schema(self, scanner, source, front, report):
        """Front matter keys and values the vault config schema allows, required ones present."""
        schema = self.schema(scanner)
        if schema.empty:
            return
        path = os.path.relpath(source.fullpath, scanner.path).replace(os.sep, '/')
        for key, message in schema.problems(front_matter_items(front) if front else [], path):
            report(self.key_line(front, key), message)

    @staticmethod
    def key_line(front, key):
        """Line of front matter key, 1 if missing."""
        return next((n for n, text in enumerate(front.splitlines(), 1)
                     if key is not None and re.match(rf'[\'"]?{re.escape(key)}[\'"]?:', text)), 1)

    def check_aliases(self, scanner, page, front, report):
        """Aliases page names win over, aliases two pages share."""
        items = dict(front_matter_items(front)) if front else {}
        key = 'aliases' if 'aliases' in items else 'alias'
        for alias in read_aliases(page.file):
            show = lambda node: os.path.relpath(node.file or node.fullpath, scanner.path).replace(os.sep, '/')
            named = [node for folderless, node in scanner.named(alias) if not folderless and node is not page]
            if named:
                report(self.key_line(front, key), f'alias {alias}: {show(named[0])} has this name, links lead there')
            for _, other in scanner.aliases.get(alias.lower(), []):
                if other is not page:
                    report(self.key_line(front, key), f'alias {alias}: also alias of {show(other)}')

    def check_file(self, scanner, page, shown):
        report = lambda line, msg: self.problems.append(f'{shown}:{line}: {msg}')
        source = page.source
        try:
            text, front, _, _ = read_parts(source.fullpath)
        except UnicodeDecodeError:
            return report(1, 'not UTF-8')
        for n, line in enumerate(front.splitlines()[1:-1], 2):
            if line and not line.startswith((' ', '-')) and ':' not in line:
                report(n, f'malformed frontmatter: {line}')
        if not front and self.FRONT_MATTER_START.match(text):
            report(1, 'unclosed frontmatter')
        self.check_schema(scanner, source, front, report)
        self.check_aliases(scanner, page, front, report)
        if page.folder and page.folder.shadowed_index() is page:
            report(1, Scanner.shadowed_message(page.folder))
        converter = CheckConverter(page, scanner, report, self.options)
        converter.read()

