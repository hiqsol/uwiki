"""Builds given folders and files of a vault into single HTML and markdown file."""

import html
import os
import re
from pathlib import Path

from .convert import Converter
from .order import Links, Order
from .vault import Filter, Selection

ASSETS = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'assets')

class UsageError(ValueError):
    """Command line options that do not go together."""

def read_asset(name):
    with open(os.path.join(ASSETS, name), encoding='utf-8') as f:
        return f.read()

class Builder:
    """Renders selected pages in reading order, folders on the way to them by title only.

    Collects links to vault pages left out of the build as `path:line: message` problems.
    """

    def __init__(self, selection, outdir='.'):
        self.selection = selection
        self.scanner = selection.scanner
        self.outdir = outdir
        self.problems = {}
        self.links = Links(self.scanner)
        self.order = Order(self.scanner, self.links)

    def inside(self, node):
        return self.selection.inside(node)

    def report(self, source, line, message):
        self.problems.setdefault(f'{self.selection.show(source)}:{line}: {message}')

    def nodes(self, folder=None):
        """Shown pages and folders in reading order, each with whether its text is built."""
        folder = folder or self.scanner.root
        yield folder, self.selection.selected(folder)
        for child in self.children(folder):
            if not self.selection.shows(child):
                continue
            if child.is_folder:
                yield from self.nodes(child)
            else:
                yield child, True

    def children(self, folder):
        return self.order.children(folder)

    def converter(self, node):
        return Converter(node, self.scanner, self.outdir, scope=self)

    def html(self, title):
        content = ''.join(self.converter(node).html(body) for node, body in self.nodes())
        return self.render('uwiki.html', {
            'title':    html.escape(title),
            'content':  content,
            'style':    read_asset('uwiki.css'),
            'script':   read_asset('uwiki.js'),
        })

    def md(self):
        return ''.join(self.converter(node).md(body) for node, body in self.nodes())

    @staticmethod
    def render(name, vars):
        return re.sub(r'\{(\w+)\}', lambda m: vars.get(m[1], m[0]), read_asset(name))

class Build:
    """Build of given folders and files into one HTML and one markdown file, as `uwiki build` takes options.

    Output is a folder, written `<title>.html` and `<title>.md` in it, or a file name:
    without extension both are written, with `.html` or `.md` only one.
    """

    KINDS = ('html', 'md')

    def __init__(self, paths, output=None, title=None, html=False, md=False, include=(), exclude=()):
        self.paths = list(paths)
        self.filter = Filter(include, exclude)
        self.outputs, self.title = self.targets(self.paths, output, title, html, md)
        self.selection = None
        self.warnings = []

    @classmethod
    def targets(cls, paths, output, title, html, md):
        """Output files by kind and title, UsageError for options that do not go together."""
        if output is None:
            if len(paths) > 1:
                raise UsageError('-o is required for several paths')
            output = '.'
        folder = os.path.isdir(output) or output.endswith(('/', os.sep))
        ext = '' if folder else os.path.splitext(output)[1].lower()
        ext = ext if ext[1:] in cls.KINDS else ''
        single = paths[0] if len(paths) == 1 and os.path.isdir(paths[0]) else None
        title = title or (Path(os.path.abspath(single)).name if single else None)
        if not folder:
            base = output[:len(output) - len(ext)]
            title = title or Path(base).name
        if not title:
            raise UsageError('--title is required with an -o folder, unless one folder is built')
        if folder:
            base = os.path.join(output, title)
        if ext:
            if html and ext != '.html' or md and ext != '.md':
                raise UsageError(f'--html and --md do not go with -o {output}')
            kinds = [ext[1:]]
        else:
            kinds = [kind for kind, on in zip(cls.KINDS, (html, md)) if on] or list(cls.KINDS)
        return {kind: f'{base}.{kind}' for kind in kinds}, title

    def scan(self):
        try:
            self.selection = Selection(self.paths, self.filter)
        except ValueError as e:
            raise UsageError(str(e)) from e
        scanner = self.selection.scanner
        scanner.root.default_title = self.title
        self.warnings = [os.path.join(self.selection.shown_root, w) for w in scanner.warnings]
        return self.selection

    def run(self):
        """Scans vault, renders and writes outputs; returns problems instead of writing if any."""
        selection = self.scan()
        outdir = os.path.dirname(os.path.abspath(next(iter(self.outputs.values()))))
        builder = Builder(selection, outdir)
        texts = {kind: builder.html(self.title) if kind == 'html' else builder.md() for kind in self.outputs}
        if builder.problems:
            return list(builder.problems)
        for kind, file in self.outputs.items():
            os.makedirs(os.path.dirname(os.path.abspath(file)), exist_ok=True)
            with open(file, 'w', encoding='utf-8') as f:
                f.write(texts[kind])
        return []
