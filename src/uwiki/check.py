"""Checks vault the way it builds: links, headings, images, frontmatter, list numbering, orphans."""

import os
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from .convert import Converter
from .vault import Filter, Scanner, Vaults

@dataclass
class CheckOptions:
    folder_links: bool = True
    orphans: bool = False
    unlinked: bool = False

class CheckConverter(Converter):
    """Converts page like renderer does, reports what would render broken."""

    IMAGE = re.compile(r'!\[[^\]]*\]\(([^)\s]+)\)')
    NUMBERED = re.compile(r'^([ \t]*)(\d+)\. ')
    LIST_BREAK = re.compile(r'^(?:[-*+] |>|#{1,6}\s)')

    def __init__(self, page, scanner, report, options):
        super().__init__(page, scanner)
        self.report = report
        self.options = options
        self.mode = 'md'
        self.lists = []  # [indent, last number] of open numbered lists, outermost first
        self.blank = False
        self.targets = set()

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
        if posixpath.normpath(posixpath.join(posixpath.dirname(self.source.path).lstrip('/'), path)).startswith('..'):
            return self.report(line, f'link leaves vault: {href}')
        target, heading = self.resolve_href(href)
        file = os.path.join(os.path.dirname(self.source.fullpath), path)
        if path and not os.path.exists(file):
            return self.report(line, f'link differs from file name: {href}' if target else f'unresolved link: {href}')
        if target is None and path.lower().endswith('.md'):
            return self.report(line, f'unresolved link: {href}')
        if target is not None:
            self.targets.add(target)
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
        name, heading, _ = self.parse_link(text)
        target = self.scanner.resolve(name, self.source.path) if name else self.source
        if target is not None:
            self.targets.add(target)
        if target is None:
            if heading or not self.attachment(text):
                self.report(self.line, f'unresolved link: [[{name}]]')
        elif heading and not heading.startswith('^'):
            node = target.page if target.is_folder else target
            if node is None or not self.section(self.read_text(node)[0], heading):
                self.report(self.line, f'missing heading: [[{name}#{heading}]]')

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
        self.links = {}  # checked page: pages it links to
        self.checked = {}  # checked page: (scanner, path to show)

    def check(self):
        for scanner, page, shown in self.vaults.files():
            self.checked[page] = scanner, shown
            self.check_file(scanner, page, shown)
        if self.options.orphans or self.options.unlinked:
            self.check_orphans()
        return self.problems

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
        links = {page: self.links[page] if page in self.links else self.page_links(scanner, page)
                 for page in scanner.pages().values()}
        linked = {target for page, targets in links.items() for target in targets if target is not page}
        if not scanner.root.page:
            return set(links), linked, linked
        reached, todo = {scanner.root}, [scanner.root]
        while todo:
            for target in links.get(todo.pop(), ()):
                if target not in reached:
                    reached.add(target)
                    todo.append(target)
        return set(links), linked, reached

    def page_links(self, scanner, page):
        converter = CheckConverter(page, scanner, lambda line, message: None, self.options)
        try:
            converter.read()
        except ValueError:
            pass
        return converter.targets

    def check_file(self, scanner, page, shown):
        report = lambda line, msg: self.problems.append(f'{shown}:{line}: {msg}')
        source = page.page if page.is_folder else page
        try:
            with open(source.fullpath, encoding='utf-8') as f:
                text = f.read()
        except UnicodeDecodeError:
            return report(1, 'not UTF-8')
        m = Converter.FRONT_MATTER.match(text)
        if m:
            for n, line in enumerate(m[0].splitlines()[1:-1], 2):
                if line and not line.startswith((' ', '-')) and ':' not in line:
                    report(n, f'malformed frontmatter: {line}')
        elif self.FRONT_MATTER_START.match(text):
            report(1, 'unclosed frontmatter')
        if page.folder and page.folder.shadowed_index() is page:
            report(1, Scanner.shadowed_message(page.folder))
        converter = CheckConverter(page, scanner, report, self.options)
        converter.read()
        self.links[page] = converter.targets

