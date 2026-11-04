"""Checks vault the way it builds: links, headings, images, frontmatter, list numbering, orphans."""

import os
import re
from dataclasses import dataclass, fields
from pathlib import Path
from urllib.parse import unquote

from .config import Config
from .convert import Converter
from .mention import Mentions
from .order import Links
from .vault import Filter, Scanner, Vaults, front_matter_items, read_aliases, read_parts

@dataclass
class CheckOptions:
    folder_links: bool = True
    orphans: bool = False
    unlisted: bool = False
    mentions: bool = False
    mentions_ignore: tuple = ()
    mentions_min_length: int = 3
    mentions_ignore_case: bool = False
    mentions_every: bool = False
    mentions_self_bold: bool = False

    @classmethod
    def from_config(cls, config):
        """Options of config `check` table and top level, as `check` takes them."""
        values = config.options('check', ())
        res = {}
        for field in fields(cls):
            key = field.name.replace('_', '-')
            if key in values:
                value = values[key]
                res[field.name] = tuple(value) if isinstance(field.default, tuple) else value
        return cls(**res)

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
        self.issues = {}  # real path of page file: [(line, message, warning)]
        self.links = {}  # scanner: links of its pages
        self.checked = {}  # checked page: (scanner, path to show)
        self.schemas = {}  # scanner: front matter schema of its vault config

    def check(self):
        for scanner, page, shown in self.vaults.files():
            self.checked[page] = scanner, shown
            self.check_file(scanner, page, shown)
        if self.options.orphans:
            self.check_orphans()
        if self.options.unlisted:
            self.check_unlisted()
        if self.options.mentions:
            self.check_mentions()
        return self.problems

    def add(self, page, shown, line, message, warning=False):
        """Reports problem or warning of page as `path:line: message`, keeps it by page file too."""
        if warning:
            self.warnings.append(f'{shown}:{line}: warning: {message}')
        else:
            self.problems.append(f'{shown}:{line}: {message}')
        file = page.file or page.source.fullpath
        self.issues.setdefault(os.path.realpath(file), []).append((line, message, warning))

    def check_mentions(self):
        """Warns about plain text mentions of another page title or alias: the first one of a page the page does not
        link, or every one with mentions_every."""
        mentions = {}
        for page, (scanner, shown) in self.checked.items():
            if scanner not in mentions:
                o = self.options
                mentions[scanner] = Mentions(scanner, o.mentions_ignore, o.mentions_min_length, o.mentions_ignore_case)
            linked = set() if self.options.mentions_every else self.targets(scanner, page)
            seen = set()
            for mention in mentions[scanner].find(page, own=self.options.mentions_self_bold):
                if mention.own:
                    self.add(page, shown, mention.line + 1, f'own term not bold: {mention.text}', True)
                    continue
                if mention.node in linked or mention.node in seen:
                    continue
                if not self.options.mentions_every:
                    seen.add(mention.node)
                self.add(page, shown, mention.line + 1, f'unlinked mention: {mention.text}', True)

    def check_unlisted(self):
        """Warns about pages and folders their folder page does not link, as contents should."""
        for page, (scanner, shown) in self.checked.items():
            folder = page.folder
            if folder is None or folder.page is None or page is scanner.root:
                continue
            if page not in self.targets(scanner, folder):
                self.add(page, shown, 1, f'not listed in {folder.page.name}.md', True)

    def vault_links(self, scanner):
        if scanner not in self.links:
            self.links[scanner] = Links(scanner)
        return self.links[scanner]

    def targets(self, scanner, page):
        """Pages and folders page links to, as build and its reading order see them."""
        return self.vault_links(scanner).targets(page)

    def check_orphans(self):
        """Pages no chain of links leads to from the root folder page, naming the reason."""
        vaults = {}
        for page, (scanner, shown) in self.checked.items():
            if scanner not in vaults:
                vaults[scanner] = self.vault_links(scanner).orphans()
            reason = vaults[scanner].get(page)
            if reason:
                self.add(page, shown, 1, f'orphan page: {reason}')

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
        report = lambda line, msg: self.add(page, shown, line, msg)
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

