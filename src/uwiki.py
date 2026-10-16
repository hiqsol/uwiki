#!/usr/bin/env python3

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
        if name in [self.name, self.singularize(self.name), 'index']:
            self.page = res
        else:
            self.children[name] = res
        return res

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

    def __init__(self, page):
        self.page = page
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
        return self.process(text)

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
            level = min(len(m[1]) + self.page.depth + 1, 6)
            line = f"{'#' * level} {m[2]}\n"
        return self.outside_code(line, self.process_links)

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
        name = match[1]
        if '|' in name:
            name, description = name.split('|', 1)
        else:
            description = titleize(name)
        return f'[{description}](#{cebabize(name)})'

    @property
    def title(self):
        if self._title:
            return self._title
        title = self.page.title
        if self.page.folder:
            pretitle = self.page.folder.title
            if pretitle != '' and self.page.folder.name != 'root':
                title = f'{pretitle} / {title}'
        self._title = title
        return title

    def html_header(self):
        tag = f'h{min(self.page.depth + 1, 6)}'
        return f'<{tag} id="{self.page.anchor}">{html.escape(self.title)}</{tag}>\n\n'

    def html(self):
        text = self.html_header()
        text += self.read()
        return markdown.markdown(text, extensions=['tables', 'fenced_code'])

    def md_header(self):
        tag = '#' * min(self.page.depth + 1, 6)
        return f'<a id="{self.page.anchor}"></a>\n\n{tag} {self.title}\n\n'

    def md(self):
        return self.md_header() + self.read().strip() + '\n\n'

class Scanner:
    def __init__(self, path, title):
        self.path = path
        self.pages = {}
        self.root = Folder(None, 'root', '', self.path)
        self.root.title = title
        self.root.anchor = 'root'

    def scan(self):
        self._scan_dir(self.root)

    def _scan_dir(self, folder):
        base = folder.fullpath
        o = sorted(os.scandir(base), key=lambda e: e.name)
        for entry in o:
            if entry.name.startswith('.'):
                continue
            fullpath = os.path.join(base, entry.name)
            name = Path(entry.name).stem
            path = os.path.join(base, name)
            part = path[len(self.path):]
            item = folder.child(entry.is_dir(), name, part, fullpath)
            if entry.is_dir():
                self._scan_dir(item)
            else:
                self.pages[name] = item

class MDRenderer:
    def __init__(self, scanner):
        self.scanner = scanner
        self.md = self.prepare()

    def prepare(self):
        self.scanner.scan()
        return self.folder2md(self.scanner.root)

    def folder2md(self, folder):
        md = Converter(folder).md()
        for child in folder.children.values():
            if child.is_folder:
                md += self.folder2md(child)
            else:
                md += Converter(child).md()
        return md

    def write(self, name):
        with open(f'{name}.md', 'w', encoding='utf-8') as f:
            f.write(self.md)

class Renderer:
    def __init__(self, scanner):
        self.scanner = scanner
        self.path = os.path.dirname(os.path.realpath(__file__))
        self.html = self.prepare()

    def prepare(self):
        self.scanner.scan()
        return self.folder2html(self.scanner.root)

    def folder2html(self, folder):
        html = Converter(folder).html()
        for child in folder.children.values():
            if child.is_folder:
                html += self.folder2html(child)
            else:
                html += Converter(child).html()
        return html

    def render(self, name, vars):
        template = self.read_file(name)
        return re.sub(r'\{(\w+)\}', lambda m: vars.get(m[1], m[0]), template)

    def read_file(self, name):
        with open(f'{self.path}/{name}', 'r', encoding='utf-8') as f:
            return f.read()

    def css_url(self): return self.url_or_path('src/uwiki.css')
    def js_url(self): return self.url_or_path('src/uwiki.js')

    def url_or_path(self, file):
        return file if self.exists(file) else self.cdn_url(file)

    def exists(self, file):
        path = os.path.join('.', file)
        return os.path.exists(path)

    def cdn_url(self, file):
        return f'https://hiqdev.com/assets/uwiki/{file}'

    def write(self, name):
        with open(f'{name}.html', 'w', encoding='utf-8') as f:
            f.write(self.render('uwiki.html', {
                'title':    html.escape(name),
                'content':  self.html,
                'style':    self.read_file('uwiki.css'),
                'script':   self.read_file('uwiki.js'),
            }))

def main():
    args = [sys.argv[0]]
    ops = []
    for i in range(1, len(sys.argv)):
        if sys.argv[i].startswith('-'):
            ops.append(sys.argv[i][1:])
        else:
            args.append(sys.argv[i])

    if len(args) < 2:
        print(f'Usage: {args[0]} <directory> [title]')
        sys.exit(1)
    path = args[1]
    title = args[2] if len(args) > 2 else Path(path).stem

    if path[0] != '/':
        path = os.path.join(os.getcwd(), path)
    scanner = Scanner(path, title)
    htmler = Renderer(scanner)
    htmler.write(title)
    mder = MDRenderer(scanner)
    mder.write(title)

if __name__ == '__main__':
    main()
