"""Reads pages, resolves wiki links, embeds and callouts into plain markdown."""

import html
import os
import re
from pathlib import Path
from urllib.parse import quote

from .vault import cebabize, titleize

class Converter:
    FENCE = re.compile(r'^\s*(```|~~~)')
    HEADING = re.compile(r'^(#{1,6})\s+(.*?)\s*$')
    CODE = re.compile(r'(`+).*?\1')
    CALLOUT = re.compile(r'^>\s*\[!([\w-]+)\]([+-]?)[ \t]*(.*?)\s*$')
    EMBED_LINE = re.compile(r'^\s*!\[\[([^\]]+)\]\]\s*$')
    IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.avif'}
    FRONT_MATTER = re.compile(r'\A---[ \t]*\r?\n.*?^(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)', re.DOTALL | re.MULTILINE)

    def __init__(self, page, scanner, outdir='.', stack=(), source=None):
        self.page = page
        self.scanner = scanner
        self.outdir = os.path.abspath(outdir)
        self.embedded = source is not None
        self.source = source or (page.page if page.is_folder and page.page else page)
        self.stack = set(stack) | {self.source.fullpath}
        self.mode = 'html'
        self.heading_ids = set()
        self.line = 0
        self._title = ''

    def read(self):
        if self.page.is_folder:
            if self.page.page is None:
                return ''
            return self.read_file(self.page.page)
        return self.read_file(self.page)

    def read_file(self, page, heading=''):
        text, start = self.read_text(page)
        if heading:
            text = self.section(text, heading)
        return self.process(text, start)

    @classmethod
    def read_text(cls, page):
        """Returns page text without front matter and number of its first line."""
        try:
            with open(page.fullpath, 'r', encoding='utf-8') as f:
                text = f.read()
        except UnicodeDecodeError as e:
            raise ValueError(f'Error reading {page.fullpath}') from e
        m = cls.FRONT_MATTER.match(text)
        if not m:
            return text, 1
        return text[m.end():], m[0].count('\n') + 1

    @classmethod
    def headings(cls, text):
        """Yields lines with their heading matches, None for non headings and fenced code."""
        fence = None
        for line in text.splitlines(keepends=True):
            f = cls.FENCE.match(line)
            if fence and f and line.lstrip().startswith(fence):
                fence = None
            elif not fence and f:
                fence = f[1]
            yield line, None if fence or f else cls.HEADING.match(line)

    @classmethod
    def section(cls, text, heading):
        """Extracts section from given heading till next heading of same or higher level."""
        res = ''
        level = 0
        for line, m in cls.headings(text):
            if m and level and len(m[1]) <= level:
                break
            if m and not level and cebabize(m[2]) == cebabize(heading):
                level = len(m[1])
            if level:
                res += line
        return res

    def process(self, text, start=1):
        res = ''
        fence = None
        lines = text.splitlines(keepends=True)
        i = 0
        while i < len(lines):
            line = lines[i]
            self.line = start + i
            i += 1
            m = self.FENCE.match(line)
            callout = self.mode == 'html' and not fence and self.CALLOUT.match(line)
            if fence:
                if m and line.lstrip().startswith(fence):
                    fence = None
                res += line
            elif m:
                fence = m[1]
                res += line
            elif callout:
                body = ''
                body_start = start + i
                while i < len(lines) and lines[i].startswith('>'):
                    body += re.sub(r'^> ?', '', lines[i])
                    i += 1
                res += self.callout(*callout.groups(), body, body_start)
            else:
                res += self.process_line(line)
        return res

    def callout(self, kind, fold, title, body, start=1):
        kind = kind.lower()
        title = self.outside_code(title, self.process_links) if title else html.escape(kind.title())
        body = self.process(body, start).strip()
        tag, title_tag = ('details', 'summary') if fold else ('div', 'div')
        open = ' open' if fold == '+' else ''
        return (
            f'\n<{tag} class="callout callout-{kind}"{open} markdown="1">\n'
            f'<{title_tag} class="callout-title" markdown="span">{title}</{title_tag}>\n\n'
            f'{body}\n\n</{tag}>\n\n'
        )

    def process_line(self, line):
        m = self.HEADING.match(line)
        if m:
            return self.heading(len(m[1]), m[2])
        m = self.EMBED_LINE.match(line)
        if m and not self.attachment(m[1]):
            return self.embed_note(m[1])
        return self.outside_code(line, self.process_links)

    def heading(self, level, text):
        level = min(level + self.page.depth + 1, 6)
        text = self.outside_code(text, self.process_links)
        if self.embedded:
            return f"{'#' * level} {text}\n"
        id = self.heading_id(text)
        if self.mode == 'md':
            return f"<a id=\"{id}\"></a>\n\n{'#' * level} {text}\n"
        return f"{'#' * level} {text} {{#{id}}}\n"

    def heading_id(self, text):
        base = self.heading_anchor(self.page, text)
        id = base
        n = 2
        while id in self.heading_ids:
            id = f'{base}-{n}'
            n += 1
        self.heading_ids.add(id)
        return id

    @staticmethod
    def heading_anchor(page, heading):
        return f'{page.anchor}--{cebabize(heading)}'

    def outside_code(self, line, func):
        res = ''
        pos = 0
        for m in self.CODE.finditer(line):
            res += func(line[pos:m.start()]) + m[0]
            pos = m.end()
        return res + func(line[pos:])

    def process_links(self, text):
        return re.sub(r'(!?)\[\[(.+?)\]\]', self.wikilink, text)

    def wikilink(self, match):
        if match[1] and self.attachment(match[2]):
            return self.embed_file(match[2])
        return self.link(match[2])

    def attachment(self, text):
        return self.scanner.attachment(text.partition('|')[0].strip(), self.source.path)

    def attachment_src(self, path):
        return quote(os.path.relpath(path, self.outdir).replace(os.sep, '/'))

    def attachment_link(self, text):
        name, _, description = text.partition('|')
        src = self.attachment_src(self.attachment(text))
        return f'[{description.strip() or Path(name.strip()).name}]({src})'

    def embed_file(self, text):
        name, _, size = text.partition('|')
        path = self.attachment(text)
        src = self.attachment_src(path)
        name = Path(name.strip()).name
        if Path(path).suffix.lower() not in self.IMAGE_EXTS:
            return f'[{name}]({src})'
        attrs = f'src="{src}"'
        m = re.fullmatch(r'(\d+)(?:x(\d+))?', size.strip())
        if m:
            attrs += f' alt="{html.escape(name)}" width="{m[1]}"'
            if m[2]:
                attrs += f' height="{m[2]}"'
        else:
            attrs += f' alt="{html.escape(size.strip() or name)}"'
        return f'<img {attrs} />'

    def embed_note(self, text):
        name, heading, _ = self.parse_link(text)
        target = self.scanner.resolve(name, self.source.path) if name else self.source
        node = target.page if target and target.is_folder else target
        if node is None or node.fullpath in self.stack:
            return self.link(text) + '\n'
        sub = Converter(self.page, self.scanner, self.outdir, self.stack, node)
        sub.mode = self.mode
        content = sub.read_file(node, heading).strip()
        if self.mode == 'md':
            return f'\n{content}\n\n'
        return f'\n<div class="embed" markdown="1">\n\n{content}\n\n</div>\n\n'

    def link(self, text):
        name, heading, description = self.parse_link(text)
        if name:
            target = self.scanner.resolve(name, self.source.path)
            if not target and not heading and self.attachment(text):
                return self.attachment_link(text)
            title = target.title if target else titleize(Path(name).name)
        else:
            target = self.page
            title = ''
        if heading and not heading.startswith('^'):
            anchor = self.heading_anchor(target, heading) if target else cebabize(heading)
            title = f'{title} > {heading}' if title else heading
        else:
            anchor = target.anchor if target else cebabize(Path(name).name)
        return f'[{description or title}](#{anchor})'

    @staticmethod
    def parse_link(text):
        """Parses `Page#Heading|description` into parts, nested headings resolve to the last one."""
        text, _, description = text.partition('|')
        name, *headings = text.split('#')
        return name.strip(), headings[-1].strip() if headings else '', description.strip()

    @property
    def title(self):
        if self._title:
            return self._title
        title = self.page.title
        if self.page.folder:
            pretitle = self.page.folder.title
            if pretitle != '' and self.page.folder.folder is not None:
                title = f'{pretitle} / {title}'
        self._title = title
        return title

    def html_header(self):
        tag = f'h{min(self.page.depth + 1, 6)}'
        return f'<{tag} id="{self.page.anchor}" class="page">{html.escape(self.title)}</{tag}>\n\n'

    def html(self):
        self.mode = 'html'
        text = self.html_header()
        text += self.read()
        import markdown
        return markdown.markdown(text, extensions=['tables', 'fenced_code', 'attr_list', 'md_in_html'])

    def md_header(self):
        tag = '#' * min(self.page.depth + 1, 6)
        return f'<a id="{self.page.anchor}"></a>\n\n{tag} {self.title}\n\n'

    def md(self):
        self.mode = 'md'
        return self.md_header() + self.read().strip() + '\n\n'

