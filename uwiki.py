#!/usr/bin/env python3

import os
import re
import sys
from pathlib import Path

import markdown

class Page:
    def __init__(self, folder, name, path, fullpath):
        self.folder = folder
        self.depth = 0
        self.name = name
        self.path = path
        self.fullpath = fullpath
        self.is_folder = False
        self.title = self.titleize(name)

    def titleize(self, name):
        return ' '.join(self.camel_split(name))
    def camel_split(self, name):
        return re.findall(r'[A-Z](?:[a-z]+|[A-Z]*(?=[A-Z]|$))', name)

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
        if name == self.name:
            self.page = res
        else:
            self.children[name] = res
        return res

    def __str__(self):
        return f'Folder(name={self.name}, title={self.title}, path={self.path})'

    def __repr__(self):
        return self.__str__()

class Converter:
    def __init__(self, page):
        self.page = page

    def read(self):
        if self.page.is_folder:
            if self.page.page is None:
                return ''
            return self.read_file(self.page.page)
        return self.read_file(self.page)

    def read_file(self, page):
        text = ''
        with open(page.fullpath, 'r', encoding='utf-8') as f:
            while True:
                line = f.readline()
                if not line:
                    break
                text += self.process_line(line)
        return text

    def process_line(self, line):
        for match in re.finditer(r'\[\[(.+?)\]\]', line):
            link = match.group(1)
            if '|' in str(link):
                link, description = link.split('|')
                line = line.replace(f'[[{link}|{description}]]', f'[{description}](#{link})')
            else:
                line = line.replace(f'[[{link}]]', f'[{link}](#{link})')
        return line

    def header(self):
        title = self.page.title
        if self.page.folder:
            pretitle = self.page.folder.title
            if pretitle != '' and self.page.folder.name != 'root':
                title = f'{pretitle} / {title}'
        tag = f'h{self.page.depth+1}'
        return f'<{tag} id="{self.page.name}">{title}</{tag}>\n'

    def html(self):
        text = self.header()
        text += self.read()
        return markdown.markdown(text, extensions=['markdown.extensions.tables', 'markdown.extensions.wikilinks'])

class Scanner:
    def __init__(self, path, title):
        self.path = path
        self.pages = {}
        self.root = Folder(None, 'root', '', self.path)
        self.root.title = title

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

class Renderer:
    def __init__(self, scanner):
        self.path = os.path.dirname(os.path.abspath(__file__))
        self.scanner = scanner
        self.html = self.prepare();

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

    def render(self, name, vars={}):
        template = self.read_template(name)
        for key, value in vars.items():
            template = template.replace(f'{{{key}}}', value)
        return template

    def read_template(self, name):
        with open(f'{self.path}/templates/{name}.tpl', 'r', encoding='utf-8') as f:
            return f.read()

    def write(self, name):
        with open(f'{name}.html', 'w', encoding='utf-8') as f:
            f.write(self.render('main.html', {
                'title': name,
                'content': self.html,
            }))

def main():
    args = sys.argv
    if len(args) < 2:
        print(f'Usage: {args[0]} <directory>')
        sys.exit(1)
    path = args[1]
    if path[0] != '/':
        path = os.path.join(os.getcwd(), path)

    title = Path(path).stem
    renderer = Renderer(Scanner(path, title))
    renderer.write(title)

if __name__ == '__main__':
    main()
