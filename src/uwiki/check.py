"""Checks vault the way it builds: links, headings, images, frontmatter, list numbering."""

import re
from pathlib import Path

from .convert import Converter
from .vault import Vaults

class CheckConverter(Converter):
    """Converts page like renderer does, reports what would render broken."""

    IMAGE = re.compile(r'!\[[^\]]*\]\(([^)\s]+)\)')
    NUMBERED = re.compile(r'^([ \t]*)(\d+)\. ')
    LIST_BREAK = re.compile(r'^(?:[-*+] |>|#{1,6}\s)')

    def __init__(self, page, scanner, report):
        super().__init__(page, scanner)
        self.report = report
        self.mode = 'md'
        self.lists = []  # [indent, last number] of open numbered lists, outermost first
        self.blank = False

    def process_line(self, line):
        self.check_numbering(line)
        return super().process_line(line)

    def process_links(self, text):
        res = super().process_links(text)
        for src in self.IMAGE.findall(text):
            if '://' not in src and not (Path(self.source.fullpath).parent / src).exists():
                self.report(self.line, f'missing image: {src}')
        return res

    def link(self, text):
        self.check_link(text)
        return super().link(text)

    def embed_note(self, text):
        self.check_link(text)
        return ''

    def check_link(self, text):
        name, heading, _ = self.parse_link(text)
        target = self.scanner.resolve(name, self.source.path) if name else self.source
        if target is None:
            if heading or not self.attachment(text):
                self.report(self.line, f'unresolved link: [[{name}]]')
        elif heading and not heading.startswith('^'):
            node = target.page if target.is_folder else target
            if node is None or not self.section(self.read_text(node)[0], heading):
                self.report(self.line, f'missing heading: [[{name}#{heading}]]')

    def check_numbering(self, line):
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
            self.report(self.line, f'list number {num}, expected {expected}')
        self.lists[-1][1] = num

class Checker:
    """Checks vault consistency the way builder sees it, reports problems as `path:line: message`."""

    FRONT_MATTER_START = re.compile(r'\A---[ \t]*\r?\n')

    def __init__(self, paths):
        self.vaults = Vaults(paths)
        self.problems = []

    def check(self):
        for scanner, page, shown in self.vaults.files():
            self.check_file(scanner, page, shown)
        return self.problems

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
        CheckConverter(page, scanner, report).read()

