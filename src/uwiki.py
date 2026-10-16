#!/usr/bin/env python3

import argparse
import html
import os
import re
import sys
from pathlib import Path

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
    FRONT_MATTER = re.compile(r'\A---[ \t]*\r?\n.*?^(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)', re.DOTALL | re.MULTILINE)

    def __init__(self, page, scanner):
        self.page = page
        self.scanner = scanner
        self.source = page.page if page.is_folder and page.page else page
        self.mode = 'html'
        self.heading_ids = set()
        self._title = ''

    def read(self):
        if self.page.is_folder:
            if self.page.page is None:
                return ''
            return self.read_file(self.page.page)
        return self.read_file(self.page)

    def read_file(self, page):
        try:
            with open(page.fullpath, 'r', encoding='utf-8') as f:
                text = f.read()
        except UnicodeDecodeError as e:
            raise ValueError(f'Error reading {page.fullpath}') from e
        return self.process(self.FRONT_MATTER.sub('', text, count=1))

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
        return self.outside_code(line, self.process_links)

    def heading(self, level, text):
        level = min(level + self.page.depth + 1, 6)
        id = self.heading_id(text)
        text = self.outside_code(text, self.process_links)
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
        return re.sub(r'\[\[(.+?)\]\]', self.link, text)

    def link(self, match):
        name, heading, description = self.parse_link(match[1])
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
        return markdown.markdown(text, extensions=['tables', 'fenced_code', 'attr_list'])

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
    def __init__(self, scanner):
        self.scanner = scanner
        self.md = self.prepare()

    def prepare(self):
        return self.folder2md(self.scanner.root)

    def folder2md(self, folder):
        md = Converter(folder, self.scanner).md()
        for child in folder.children.values():
            if child.is_folder:
                md += self.folder2md(child)
            else:
                md += Converter(child, self.scanner).md()
        return md

    def write(self, filename):
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(self.md)

class Renderer:
    def __init__(self, scanner):
        self.scanner = scanner
        self.path = os.path.dirname(os.path.realpath(__file__))
        self.html = self.prepare()

    def prepare(self):
        return self.folder2html(self.scanner.root)

    def folder2html(self, folder):
        html = Converter(folder, self.scanner).html()
        for child in folder.children.values():
            if child.is_folder:
                html += self.folder2html(child)
            else:
                html += Converter(child, self.scanner).html()
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
        Renderer(scanner).write(f'{output}.html', title)
    if args.md or both:
        MDRenderer(scanner).write(f'{output}.md')

if __name__ == '__main__':
    main()
