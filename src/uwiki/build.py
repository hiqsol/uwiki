"""Builds single HTML and markdown file from a vault."""

import html
import os
import re

from .convert import Converter

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
        self.path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'assets')
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

