#!/usr/bin/env python3

import os
import re
import sys
from pathlib import Path

import markdown

class Page:
    def __init__(self, folder, name, path, fullpath):
        self.folder = folder
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

    def child(self, is_folder, name, path, fullpath):
        if is_folder:
            return Folder(self, name, path, fullpath)
        else:
            return Page(self, name, path, fullpath)

    def __str__(self):
        return f'Folder(name={self.name}, title={self.title}, path={self.path})'

    def __repr__(self):
        return self.__str__()

class Converter:
    def __init__(self, page):
        self.page = page

    def read(self):
        text = ''
        with open(self.page.fullpath, 'r', encoding='utf-8') as f:
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

    def header(self): # with anchor
        title = self.page.title
        if title != self.page.folder.title:
            title = f'{self.page.folder.title} / {title}'
        return f'<h2 id="{self.page.name}">{title}</h2>'

    def html(self):
        text = self.header()
        text += self.read()
        return markdown.markdown(text, extensions=['markdown.extensions.tables', 'markdown.extensions.wikilinks'])

class Scanner:
    def __init__(self, path):
        self.path = path
        self.pages = {}

    def scan(self):
        folder = Folder(None, 'root', 'ROOT', self.path)
        self._scan_dir(folder)

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
        html = ''
        for page in self.scanner.pages.values():
            html += Converter(page).html()
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

    renderer = Renderer(Scanner(path))
    renderer.write(Path(path).stem)

if __name__ == '__main__':
    main()
