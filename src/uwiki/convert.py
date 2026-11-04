"""Reads pages, resolves wiki links, embeds and callouts into plain markdown."""

import functools
import html
import os
import re
from pathlib import Path
from urllib.parse import quote, unquote

from . import render
from .vault import FRONT_MATTER, TITLE, cebabize, read_aliases, read_text, titleize

class Converter:
    FENCE = re.compile(r'^\s*(```|~~~)')
    HEADING = re.compile(r'^(#{1,6})\s+(.*?)\s*$')
    CODE = re.compile(r'(`+).*?\1')
    TITLE = TITLE
    CALLOUT = re.compile(r'^>\s*\[!([\w-]+)\]([+-]?)[ \t]*(.*?)\s*$')
    WIKILINK = re.compile(r'(!?)\[\[(.+?)\]\]')
    MD_LINK = re.compile(r"""(`+).*?\1|(?<!!)\[([^\]]*)\]\(([^)\s]+)(?:[ \t]+(?:"[^"]*"|'[^']*'))?\)""")
    LINK_DEF = re.compile(r'^ {0,3}\[[^\]]+\]:[ \t]*(<[^>\s]*>|\S+)')
    BLOCK_START = re.compile(r'^\s*(?:[-*+] |\d+[.)] |>|#{1,6}\s|```|~~~)')
    EMBED_LINE = re.compile(r'^\s*!\[\[([^\]]+)\]\]\s*$')
    NUMBERED = re.compile(r'^([ \t]*)(\d+)[.)]([ \t]+)')
    LIST_BREAK = re.compile(r'^(?:[-*+] |>|#{1,6}\s)')
    ITEM = re.compile(r'\d+(?:\.\d+)*')
    BOLD = re.compile(r'\*\*([^*\n]+?)\*\*')
    BLOCK_PREFIX = re.compile(r'^[ \t]*(?:>[ \t]?)*(?:(?:[-*+]|\d+[.)])[ \t]+(?:\[[ xX]\][ \t]+)?)?(?:#{1,6}[ \t]+)?'
                              r'(?:\|[ \t]*)?')
    IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.avif'}
    FRONT_MATTER = FRONT_MATTER

    def __init__(self, page, scanner, outdir='.', stack=(), source=None, scope=None):
        self.page = page
        self.scanner = scanner
        self.scope = scope  # build scope: inside(node) tells links it can lead to, report(source, line, message)
        self.outdir = os.path.abspath(outdir)
        self.embedded = source is not None
        self.source = source or (page.page if page.is_folder and page.page else page)
        self.stack = set(stack) | {self.source.fullpath}
        self.mode = 'html'
        self.heading_ids = set()
        self.line = 0
        self._title = ''
        self.shift = 0
        self.item_lines = {}  # line number: (number path, sections whose first list it is in)
        self.problems = {}  # line number: [(message, warning)] check reports, marked in HTML at their line
        self.lines = []  # source line of every line process gave last, None for lines not of the page

    def read(self):
        node = self.page.source
        if node is None:
            return ''
        text, start = self.read_text(node)
        m = self.title_heading(text, self.page)
        if m:
            text = m[1] + '\n' + text[m.end():]
            level = len(m[2])
            if all(not h or len(h[1]) > level for _, h in self.headings(text)):
                self.shift = level
        if not self.embedded:
            self.item_lines = {start + i: (path, keys) for i, path, keys in self.list_items(text)}
        return self.process(text, start)

    @classmethod
    def title_heading(cls, text, page):
        """Leading heading that is or repeats page title, page header replaces it."""
        m = cls.TITLE.match(text)
        return m if m and cebabize(m[3]) == cebabize(page.title) else None

    def read_file(self, page, heading=''):
        text, start = self.read_text(page)
        if heading:
            text = self.section(text, heading)
        return self.process(text, start)

    @staticmethod
    def read_text(page):
        return read_text(page.fullpath)

    @classmethod
    def fenced(cls, lines):
        """Yields lines with whether they are fenced code, fences included."""
        fence = None
        for line in lines:
            f = cls.FENCE.match(line)
            if fence:
                if f and line.lstrip().startswith(fence):
                    fence = None
                yield line, True
            elif f:
                fence = f[1]
                yield line, True
            else:
                yield line, False

    @classmethod
    def prose(cls, text):
        """Line indexes and lines outside fenced code."""
        for i, (line, code) in enumerate(cls.fenced(text.splitlines())):
            if not code:
                yield i, line

    @classmethod
    def headings(cls, text):
        """Yields lines with their heading matches, None for non headings and fenced code."""
        for line, code in cls.fenced(text.splitlines(keepends=True)):
            yield line, None if code else cls.HEADING.match(line)

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

    @classmethod
    def list_items(cls, text):
        """Yields line index, number path and sections of items of the first numbered list of the page
        (section '') and of the first one under every heading (its text): `3`, nested `3.2`."""
        section, sections = '', set()
        page = False
        stack, keys, blank = [], [], False
        for i, line in cls.prose(text):
            h = cls.HEADING.match(line)
            m = cls.NUMBERED.match(line)
            if h:
                section, stack = h[2], []
            elif m:
                indent = len(m[1].expandtabs(4))
                if not stack:
                    keys = [] if page else ['']
                    page = True
                    if section and cebabize(section) not in sections:
                        keys.append(section)
                        sections.add(cebabize(section))
                while stack and stack[-1][0] > indent:
                    stack.pop()
                if not stack or stack[-1][0] < indent:
                    stack.append([indent, 0])
                stack[-1][1] += 1
                if keys:
                    yield i, '.'.join(str(n) for _, n in stack), keys
            elif line.strip() and not line[0].isspace() and (blank or cls.LIST_BREAK.match(line)):
                stack = []
            blank = not line.strip()

    @classmethod
    def find_item(cls, page, heading, item):
        """Whether page has item by number path in its first numbered list, or the first one under heading."""
        return (item, cebabize(heading) if heading else '') in cls.item_keys(cls.read_text(page)[0])

    @staticmethod
    @functools.lru_cache(maxsize=4096)
    def item_keys(text):
        """Number paths of list items with anchors of sections they are in, once per text links look into."""
        return frozenset((path, cebabize(key) if key else '')
                         for _, path, keys in Converter.list_items(text) for key in keys)

    @classmethod
    def alias_item(cls, page, alias):
        """Number path and section of the linkable item alias is first bold in, links by alias lead there, None if none."""
        return cls.bold_items(cls.read_text(page)[0]).get(cebabize(alias))

    @staticmethod
    @functools.lru_cache(maxsize=4096)
    def bold_items(text):
        """Bold terms, singular ones too, as anchors: number path and section of the item each is first bold in."""
        items = {i: (path, keys[-1]) for i, path, keys in Converter.list_items(text)}
        res, current = {}, None
        for i, line in Converter.prose(text):
            if i in items:
                current = items[i]
            elif Converter.HEADING.match(line) or line.strip() and not line[0].isspace():
                current = None
            for m in Converter.BOLD.finditer(line) if current else ():
                term = cebabize(m[1])
                singular = term[:-3] + 'y' if term.endswith('ies') else term[:-1] if term.endswith('s') else term
                res.setdefault(term, current)
                res.setdefault(singular, current)
        return res

    def title_section(self, target, heading):
        """Heading of a section, none for the title heading the page header replaces."""
        return '' if heading and self.anchor(target, heading) == target.anchor else heading

    def item_anchor(self, target, heading, item):
        """Anchor of item: of the target page, or of its heading section."""
        return f'{self.anchor(target, heading) if heading else target.anchor}--{item}'

    def item_anchors(self, line):
        """Line of numbered list item with anchors of its number path put after the number."""
        path, keys = self.item_lines[self.line]
        m = self.NUMBERED.match(line)
        ids = [self.item_anchor(self.page, key, path) for key in keys]
        if self.mode == 'md':
            anchors = ''.join(f'<a id="{id}"></a>' for id in ids)
        else:
            anchors = f'<a class="item-anchor" id="{ids[-1]}"></a>'  # the page links it and shows its number
            anchors += ''.join(f'<a id="{id}"></a>' for id in ids[:-1])
        anchors += ''.join(f'<a id="{id}"></a>' for id in self.alias_anchors(path, keys[-1]))
        return line[:m.end()] + anchors + line[m.end():]

    def alias_anchors(self, path, key):
        """Anchors of page aliases item defines in bold, `page--alias`, besides its number ones."""
        source = self.page.source
        return [self.heading_anchor(self.page, alias) for alias in read_aliases(self.page.file)
                if source is not None and self.alias_item(source, alias) == (path, key)]

    def process(self, text, start=1):
        """Text as markdown for the renderer, `lines` the source line of each of its lines:
        lines become lines one to one, others, as an embedded page, are of no line."""
        res, at = '', []
        fence = None
        lines = text.splitlines(keepends=True)
        i = 0
        while i < len(lines):
            line = lines[i]
            self.line = first = start + i
            i += 1
            m = self.FENCE.match(line)
            callout = self.mode == 'html' and not fence and self.CALLOUT.match(line)
            if fence:
                if m and line.lstrip().startswith(fence):
                    fence = None
                out = line
            elif m:
                fence = m[1]
                out = line
            elif callout:
                body = ''
                body_start = start + i
                while i < len(lines) and lines[i].startswith('>'):
                    body += re.sub(r'^> ?', '', lines[i])
                    i += 1
                out = self.callout(*callout.groups(), body, body_start)
            else:
                while (self.open_bracket(line) and not self.HEADING.match(line) and i < len(lines)
                       and lines[i].strip() and not self.BLOCK_START.match(lines[i])):
                    line += lines[i]
                    i += 1
                out = self.mark_problems(self.process_line(line), self.line, line.count('\n') or 1)
            src = self.lines if callout else list(range(first, start + i))
            n = self.count_lines(out)
            at += src if len(src) == n else [None] * n
            res += out
        self.lines = at
        return res

    @staticmethod
    def count_lines(text):
        return text.count('\n') + (1 if text and not text.endswith('\n') else 0)

    def mark_problems(self, text, start, count):
        """Text with a marker of problems of its lines after its block prefix, as list item or heading."""
        lines = [n for n in range(start, start + count) if n in self.problems]
        if not lines or self.mode != 'html' or not text.strip():
            return text
        markers = ''.join(self.problem_marker(n) for n in lines)
        at = self.BLOCK_PREFIX.match(text).end()
        return text[:at] + markers + text[at:]

    def problem_marker(self, line):
        warning = all(w for _, w in self.problems[line])
        title = html.escape('\n'.join(f'{line}: {m}' for m, _ in self.problems[line])).replace('\n', '&#10;')
        kind = 'warning' if warning else 'problem'
        return f'<span class="problem-at {kind}" id="problem-{self.page.anchor}-{line}" title="{title}"></span>'

    @classmethod
    def open_bracket(cls, text):
        """Whether text leaves link text open, as link text wrapped to the next line does."""
        text = cls.CODE.sub('', text.replace('\\[', '').replace('\\]', ''))
        return text.count('[') > text.count(']')

    def callout(self, kind, fold, title, body, start=1):
        """Callout as HTML block around its body, `lines` its title line for the block, the lines of the body."""
        line = self.line
        kind = kind.lower()
        title = render.inline(self.links(title)) if title else html.escape(kind.title())
        text = self.process(body, start)
        body = text.strip()
        skipped = text[:len(text) - len(text.lstrip())].count('\n')  # blank lines strip drops
        body_lines = (self.lines[skipped:] + [None] * (body.count('\n') + 1))[:body.count('\n') + 1]
        self.lines = [line] * 4 + body_lines + [None] * 3
        tag, title_tag = ('details', 'summary') if fold else ('div', 'div')
        open = ' open' if fold == '+' else ''
        return (
            f'\n<{tag} class="callout callout-{kind}"{open}>\n'
            f'<{title_tag} class="callout-title">{title}</{title_tag}>\n\n'
            f'{body}\n\n</{tag}>\n\n'
        )

    def process_line(self, line):
        m = self.HEADING.match(line)
        if m:
            return self.heading(len(m[1]), m[2])
        m = self.EMBED_LINE.match(line)
        if m and not self.attachment(m[1]):
            return self.embed_note(m[1])
        if self.LINK_DEF.match(line):
            return self.LINK_DEF.sub(self.link_definition, line, count=1)
        if self.line in self.item_lines and self.NUMBERED.match(line):
            line = self.item_anchors(line)
        return self.links(line)

    def heading(self, level, text):
        level = min(level - self.shift + self.page.depth + 1, 6)
        text = self.links(text)
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

    def links(self, text):
        return self.outside_code(self.MD_LINK.sub(self.markdown_link, text), self.process_links)

    def markdown_link(self, match):
        if match[1]:
            return match[0]
        href = self.local_href(match[3], self.line + match.string.count('\n', 0, match.start()))
        return match[0] if href is None else f'[{match[2]}]({href})'

    def link_definition(self, match):
        """Reference link definition `[ref]: path.md#heading` points where inline link would."""
        href = self.local_href(match[1].strip('<>'), self.line)
        return match[0] if href is None else match[0][:match.start(1) - match.start()] + href

    def local_href(self, href, line=None):
        """Anchor of vault page or heading relative link points at, None for other links."""
        if not self.is_local(href):
            return None
        target, heading = self.resolve_href(href)
        if target is None:
            return None
        self.check_scope(target, href, line)
        fragment = unquote(href).partition('#')[2]
        if self.ITEM.fullmatch(fragment):
            return '#' + self.item_anchor(target, '', fragment)
        return '#' + (self.anchor(target, heading) if heading else target.anchor)

    def check_scope(self, target, link, line=None, embed=False):
        """Reports link to vault page build leaves out."""
        if self.scope and target is not None and not self.scope.inside(target):
            kind = 'embed' if embed else 'link'
            self.scope.report(self.source, self.line if line is None else line,
                              f'{kind} outside built paths: {link}')

    def anchor(self, target, heading):
        """Heading anchor in target, page anchor for the title heading it drops."""
        node = target.source
        m = node and self.title_heading(self.read_text(node)[0], target)
        if m and cebabize(m[3]) == cebabize(heading):
            return target.anchor
        return self.heading_anchor(target, heading)

    @staticmethod
    def is_local(href):
        """Whether href is path relative to the page, or just fragment."""
        path = href.partition('#')[0]
        return ':' not in path and not path.startswith('/')

    def resolve_href(self, href):
        """Finds target of relative markdown link and heading its fragment slug names, if any."""
        path, _, fragment = unquote(href).partition('#')
        target = self.scanner.resolve_path(path, self.source.path) if path else self.page
        if target is None or not fragment:
            return target, ''
        node = target.source if path else self.source
        return target, node and self.find_heading(node, fragment)

    @classmethod
    def find_heading(cls, page, slug):
        """Heading GitHub and GitLab anchor as slug, repeated ones as slug-1, slug-2..., or uwiki does."""
        slug = slug.lower()
        return next((heading for anchor, cebab, heading in cls.heading_keys(cls.read_text(page)[0])
                     if slug in (anchor, cebab)), None)

    @staticmethod
    @functools.lru_cache(maxsize=4096)
    def heading_keys(text):
        """GitHub anchor, uwiki anchor and text of every heading, once per text links look into."""
        seen, res = {}, []
        for _, m in Converter.headings(text):
            if m:
                base = Converter.slug(m[2])
                res.append((f'{base}-{seen[base]}' if base in seen else base, cebabize(m[2]), m[2]))
                seen[base] = seen.get(base, 0) + 1
        return tuple(res)

    @staticmethod
    def slug(heading):
        """Heading anchor as GitHub and GitLab make it from rendered heading text."""
        text = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', heading)
        text = re.sub(r'<[^>]*>|(?<!\w)_+|_+(?!\w)', '', text)
        return re.sub(r'[^\w\- ]', '', text.lower()).replace(' ', '-')

    @classmethod
    def outside_code(cls, line, func):
        res = ''
        pos = 0
        for m in cls.CODE.finditer(line):
            res += func(line[pos:m.start()]) + m[0]
            pos = m.end()
        return res + func(line[pos:])

    def process_links(self, text):
        return self.WIKILINK.sub(self.wikilink, text)

    def wikilink(self, match):
        if match[1] and self.attachment(match[2]):
            return self.embed_file(match[2])
        return self.link(match[2])

    def attachment(self, text):
        return self.scanner.attachment(text.partition('|')[0].removesuffix('\\').strip(), self.source.path)

    def attachment_src(self, path):
        """Attachment path relative to output, or under the URL a server serves vault files at."""
        base = getattr(self.scope, 'attachment_base', None)
        if base:
            return base + quote(os.path.relpath(path, self.scanner.path).replace(os.sep, '/'))
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
        name, heading, item, _ = self.parse_target(text)
        if item:
            return self.link(text) + '\n'
        target = self.scanner.resolve(name, self.source.path) if name else self.source
        node = target and target.source
        if node is not None and self.scope and not self.scope.inside(target):
            self.check_scope(target, f'![[{text}]]', embed=True)
            return self.link(text, checked=True) + '\n'
        if node is None or node.fullpath in self.stack:
            return self.link(text) + '\n'
        sub = Converter(self.page, self.scanner, self.outdir, self.stack, node, self.scope)
        sub.mode = self.mode
        content = sub.read_file(node, heading).strip()
        if self.mode == 'md':
            return f'\n{content}\n\n'
        return f'\n<div class="embed">\n\n{content}\n\n</div>\n\n'

    def link(self, text, checked=False):
        name, heading, item, description = self.parse_target(text)
        if name:
            target, aliased = self.scanner.lookup(name, self.source.path)
            if not target and not heading and self.attachment(text):
                return self.attachment_link(text)
            if not checked:
                self.check_scope(target, f'[[{text}]]')
            if aliased:
                title = name
                found = not heading and not item and target.source and self.alias_item(target.source, name)
                if found:
                    return f'[{description or title}](#{self.item_anchor(target, found[1], found[0])})'
            elif self.names_folder_page(target, name):
                # [[Card]] to folder page Card.md of Cards/ goes by the page's own title, [[Cards]] by the folder's
                title = target.page.title
            else:
                title = target.title if target else titleize(Path(name).name)
        else:
            target = self.page
            title = ''
        if item and target:
            anchor = self.item_anchor(target, heading, item)
            # as written: Page#3, Page#Heading#3, #3 on the same page
            title = '#'.join([title, *filter(None, [heading]), item])
        elif heading and not heading.startswith('^'):
            anchor = self.anchor(target, heading) if target else cebabize(heading)
            title = f'{title} > {heading}' if title else heading
        else:
            anchor = target.anchor if target else cebabize(Path(name).name)
        return f'[{description or title}](#{anchor})'

    @staticmethod
    def names_folder_page(target, name):
        """Whether a link names folder page `Card.md` of `Cards/` rather than the folder, README and index aside."""
        if not (target and target.is_folder and target.page):
            return False
        page = target.page.name.lower()
        return page == Path(name).name.lower() != target.name.lower() and page not in ('index', 'readme')

    @classmethod
    def parse_target(cls, text):
        """Parses `Page#Heading#3|description` into name, heading, item number path and description,
        `Page\\|description` too, as a table cell escapes its pipe."""
        text, _, description = text.partition('|')
        text = text.removesuffix('\\')
        name, *parts = [part.strip() for part in text.split('#')]
        item = parts.pop() if parts and cls.ITEM.fullmatch(parts[-1]) else ''
        return name, parts[-1] if parts else '', item, description.strip()

    @property
    def folders(self):
        """Folders above the page, top one first, root left out."""
        folders = []
        folder = self.page.folder
        while folder and folder.folder:
            folders.insert(0, folder)
            folder = folder.folder
        return folders

    @property
    def title(self):
        if not self._title:
            self._title = ' / '.join([folder.title for folder in self.folders] + [self.page.title])
        return self._title

    def html_header(self, aside=''):
        """Folders as links above the page title, aside HTML after it."""
        tag = f'h{min(self.page.depth + 1, 6)}'
        aliases = ', '.join(read_aliases(self.page.file))
        aliases = f' data-aliases="{html.escape(aliases)}"' if aliases else ''
        crumb = ' / '.join(f'<a href="#{folder.anchor}">{html.escape(folder.title)}</a>' for folder in self.folders)
        crumb = f'<span class="crumb">{crumb}</span>' if crumb else ''
        return (f'<{tag} id="{self.page.anchor}" class="page" data-title="{html.escape(self.page.title)}"{aliases}>'
                f'{crumb}{html.escape(self.page.title)}{aside}</{tag}>\n\n')

    def html(self, body=True, aside='', lines=False):
        """Page header with aside HTML in it and text as HTML, header only without body;
        with lines, blocks carry `data-line` of the source line they start at."""
        self.mode = 'html'
        text = self.html_header(aside)
        at = [None] * self.count_lines(text)
        if body:
            text += self.read()
            at += self.lines
        return render.html(text, at if lines else None)

    def md_header(self):
        tag = '#' * min(self.page.depth + 1, 6)
        return f'<a id="{self.page.anchor}"></a>\n\n{tag} {self.title}\n\n'

    def md(self, body=True):
        """Page header and text as markdown, header only without body."""
        self.mode = 'md'
        return self.md_header() + (self.read().strip() + '\n\n' if body else '')

