#!/usr/bin/env python3

import argparse
import html
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

import markdown

def titleize(name):
    words = camel_split(name, r'[\s_-]+')
    if not words:
        return name
    return ' '.join(w[0].upper() + w[1:] for w in words)
def cebabize(name):
    return '-'.join(camel_split(name)).lower() or 'page'
def camel_split(name, separators=r'[\W_]+'):
    """Splits `MyPage`, `my notes`, `my-notes`, `HTMLParser`, `2024Plans` into words."""
    words = []
    for chunk in re.split(separators, name):
        word = ''
        for i, c in enumerate(chunk):
            prev = chunk[i-1] if i else ''
            next = chunk[i+1] if i+1 < len(chunk) else ''
            if word and (
                (c.isupper() and (prev.islower() or prev.isdigit() or (prev.isupper() and next.islower())))
                or (c.isdigit() and prev.isalpha())
            ):
                words.append(word)
                word = ''
            word += c
        if word:
            words.append(word)
    return words

class Page:
    def __init__(self, folder, name, path, fullpath):
        self.folder = folder
        self.depth = 0
        self.name = name
        self.path = path
        self.fullpath = fullpath
        self.is_folder = False
        self.title = titleize(name)
        self.anchor = cebabize(name)

    def __str__(self):
        return f'Page(name={self.name}, title={self.title}, path={self.path})'
    def __repr__(self):
        return self.__str__()

class Folder(Page):
    def __init__(self, folder, name, path, fullpath):
        super().__init__(folder, name, path, fullpath)
        self.is_folder = True
        self.children = {}
        self.page = None

    def build_child(self, is_folder, name, path, fullpath):
        if is_folder:
            return Folder(self, name, path, fullpath)
        else:
            return Page(self, name, path, fullpath)

    def child(self, is_folder, name, path, fullpath):
        res = self.build_child(is_folder, name, path, fullpath)
        res.depth = self.depth + 1
        if not is_folder and self.page is None and self.is_index(name):
            self.page = res
        else:
            self.children[name] = res
        return res

    def is_index(self, name):
        name = name.lower()
        return name in [self.name.lower(), self.singularize(self.name.lower()), 'index']

    def is_empty(self):
        return self.page is None and not self.children

    def singularize(self, name):
        if name.endswith('ies'):
            return name[:-3] + 'y'
        if name.endswith('s'):
            return name[:-1]
        return name

    def __str__(self):
        return f'Folder(name={self.name}, title={self.title}, path={self.path})'

    def __repr__(self):
        return self.__str__()

class Converter:
    FENCE = re.compile(r'^\s*(```|~~~)')
    HEADING = re.compile(r'^(#{1,6})\s+(.*?)\s*$')
    CODE = re.compile(r'(`+).*?\1')
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
        self._title = ''

    def read(self):
        if self.page.is_folder:
            if self.page.page is None:
                return ''
            return self.read_file(self.page.page)
        return self.read_file(self.page)

    def read_file(self, page, heading=''):
        try:
            with open(page.fullpath, 'r', encoding='utf-8') as f:
                text = f.read()
        except UnicodeDecodeError as e:
            raise ValueError(f'Error reading {page.fullpath}') from e
        text = self.FRONT_MATTER.sub('', text, count=1)
        if heading:
            text = self.section(text, heading)
        return self.process(text)

    def section(self, text, heading):
        """Extracts section from given heading till next heading of same or higher level."""
        res = ''
        level = 0
        fence = None
        for line in text.splitlines(keepends=True):
            f = self.FENCE.match(line)
            if fence and f and line.lstrip().startswith(fence):
                fence = None
            elif not fence and f:
                fence = f[1]
            m = None if fence or f else self.HEADING.match(line)
            if m and level and len(m[1]) <= level:
                break
            if m and not level and cebabize(m[2]) == cebabize(heading):
                level = len(m[1])
            if level:
                res += line
        return res

    def process(self, text):
        res = ''
        fence = None
        for line in text.splitlines(keepends=True):
            m = self.FENCE.match(line)
            if fence:
                if m and line.lstrip().startswith(fence):
                    fence = None
                res += line
            elif m:
                fence = m[1]
                res += line
            else:
                res += self.process_line(line)
        return res

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

    def embed_file(self, text):
        name, _, size = text.partition('|')
        path = self.attachment(text)
        src = quote(os.path.relpath(path, self.outdir).replace(os.sep, '/'))
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
        return markdown.markdown(text, extensions=['tables', 'fenced_code', 'attr_list', 'md_in_html'])

    def md_header(self):
        tag = '#' * min(self.page.depth + 1, 6)
        return f'<a id="{self.page.anchor}"></a>\n\n{tag} {self.title}\n\n'

    def md(self):
        self.mode = 'md'
        return self.md_header() + self.read().strip() + '\n\n'

class Scanner:
    def __init__(self, path, title):
        self.path = path
        self.root = Folder(None, Path(path).name, '', self.path)
        self.root.title = title
        self.root.anchor = 'root'
        self.targets = {}
        self.attachments = {}

    def scan(self):
        self._scan_dir(self.root)
        self._index(self.root)
        self._assign_anchors()

    def _scan_dir(self, folder):
        base = folder.fullpath
        o = sorted(os.scandir(base), key=lambda e: e.name)
        for entry in o:
            if entry.name.startswith('.'):
                continue
            fullpath = os.path.join(base, entry.name)
            if entry.is_dir():
                item = folder.child(True, entry.name, fullpath[len(self.path):], fullpath)
                self._scan_dir(item)
                if item.is_empty():
                    del folder.children[item.name]
            elif entry.name.endswith('.md'):
                name = Path(entry.name).stem
                folder.child(False, name, fullpath[len(self.path):-3], fullpath)
            else:
                self.attachments.setdefault(entry.name.lower(), []).append(fullpath)

    def _index(self, folder):
        """Registers link targets: pages, folders and folder pages, the latter resolve to the folder."""
        if folder.page:
            self._add_target(folder.page.path, folder)
        if folder.folder:
            self._add_target(folder.path, folder)
        for child in folder.children.values():
            if child.is_folder:
                self._index(child)
            else:
                self._add_target(child.path, child)

    def _add_target(self, path, node):
        self.targets.setdefault(Path(path).name.lower(), []).append((path.lower(), node))

    def _assign_anchors(self):
        """Anchors are made from names, from paths for clashing names."""
        nodes = {}
        for entries in self.targets.values():
            for _, node in entries:
                if node is not self.root:
                    nodes[id(node)] = node
        groups = {}
        for node in nodes.values():
            groups.setdefault(cebabize(node.name), []).append(node)
        used = {'root'}
        clashing = []
        for anchor, group in groups.items():
            if len(group) == 1 and anchor not in used:
                group[0].anchor = anchor
                used.add(anchor)
            else:
                clashing += group
        for node in clashing:
            anchor = cebabize(node.path)
            unique = anchor
            n = 2
            while unique in used:
                unique = f'{anchor}-{n}'
                n += 1
            node.anchor = unique
            used.add(unique)

    def attachment(self, name, source=''):
        """Finds attachment file by name or path, prefers ones near the source page."""
        name = name.strip().strip('/')
        near = os.path.join(self.path, str(Path(source).parent).strip('/'), '')
        candidates = [
            (not path.startswith(near), path.count('/'), path)
            for path in self.attachments.get(Path(name).name.lower(), [])
            if path.lower().endswith('/' + name.lower())
        ]
        return min(candidates)[2] if candidates else None

    def resolve(self, name, source=''):
        """Finds link target by name or path like Obsidian does.

        Prefers targets near the source page, then shortest path.
        """
        near = str(Path(source).parent).lower().rstrip('/') + '/'
        name = name.strip().strip('/').lower()
        if name.endswith('.md'):
            name = name[:-3]
        candidates = [
            (not path.startswith(near), path.count('/'), path, node)
            for path, node in self.targets.get(Path(name).name, [])
            if path.endswith('/' + name)
        ]
        return min(candidates, key=lambda c: c[:3])[3] if candidates else None

class MDRenderer:
    def __init__(self, scanner, outdir='.'):
        self.scanner = scanner
        self.outdir = outdir
        self.md = self.prepare()

    def prepare(self):
        return self.folder2md(self.scanner.root)

    def folder2md(self, folder):
        md = Converter(folder, self.scanner, self.outdir).md()
        for child in folder.children.values():
            if child.is_folder:
                md += self.folder2md(child)
            else:
                md += Converter(child, self.scanner, self.outdir).md()
        return md

    def write(self, filename):
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(self.md)

class Renderer:
    def __init__(self, scanner, outdir='.'):
        self.scanner = scanner
        self.outdir = outdir
        self.path = os.path.dirname(os.path.realpath(__file__))
        self.html = self.prepare()

    def prepare(self):
        return self.folder2html(self.scanner.root)

    def folder2html(self, folder):
        html = Converter(folder, self.scanner, self.outdir).html()
        for child in folder.children.values():
            if child.is_folder:
                html += self.folder2html(child)
            else:
                html += Converter(child, self.scanner, self.outdir).html()
        return html

    def render(self, name, vars):
        template = self.read_file(name)
        return re.sub(r'\{(\w+)\}', lambda m: vars.get(m[1], m[0]), template)

    def read_file(self, name):
        with open(f'{self.path}/{name}', 'r', encoding='utf-8') as f:
            return f.read()

    def write(self, filename, name):
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(self.render('uwiki.html', {
                'title':    html.escape(name),
                'content':  self.html,
                'style':    self.read_file('uwiki.css'),
                'script':   self.read_file('uwiki.js'),
            }))

def main():
    parser = argparse.ArgumentParser(description='Renders folder of markdown files to single HTML file.')
    parser.add_argument('directory', help='folder with markdown files, e.g. Obsidian vault')
    parser.add_argument('title', nargs='?', help='title and output file name, default: folder name')
    parser.add_argument('--html', action='store_true', help='write HTML (default: both HTML and markdown)')
    parser.add_argument('--md', action='store_true', help='write single markdown file')
    parser.add_argument('-o', '--output', default='.', help='output directory, default: current')
    args = parser.parse_args()

    path = os.path.abspath(args.directory)
    if not os.path.isdir(path):
        parser.error(f'not a directory: {args.directory}')
    title = args.title or Path(path).name
    both = not args.html and not args.md
    os.makedirs(args.output, exist_ok=True)
    output = os.path.join(args.output, title)

    scanner = Scanner(path, title)
    scanner.scan()
    if args.html or both:
        Renderer(scanner, args.output).write(f'{output}.html', title)
    if args.md or both:
        MDRenderer(scanner, args.output).write(f'{output}.md')

if __name__ == '__main__':
    main()
