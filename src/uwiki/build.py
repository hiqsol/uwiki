"""Builds given folders and files of a vault into single HTML and markdown file."""

import html
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from .check import Checker, CheckOptions
from .config import Config
from .convert import Converter
from .order import Links, Order
from .stats import Stats
from .vault import Filter, Selection, cebabize, read_front_matter, read_parts

ASSETS = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'assets')

class UsageError(ValueError):
    """Command line options that do not go together."""

def read_asset(name):
    with open(os.path.join(ASSETS, name), encoding='utf-8') as f:
        return f.read()

@dataclass
class BuildOptions:
    backlinks: bool = True
    front_matter: bool = True
    live_reload: bool = False  # served only: page reloads after a rebuild
    attachment_base: str = ''  # served only: URL attachments are served at

class Builder:
    """Renders selected pages in reading order, folders on the way to them by title only.

    Collects links to vault pages left out of the build as `path:line: message` problems.
    """

    SEP = ' › '

    def __init__(self, selection, outdir='.', options=None, build_id='', issues=None):
        self.selection = selection
        self.scanner = selection.scanner
        self.outdir = outdir
        self.options = options or BuildOptions()
        self.attachment_base = self.options.attachment_base
        self.build_id = build_id
        self.problems = {}
        self.issues = issues or {}  # real path of page file: [(line, message, warning)] check reports
        self.links = Links(self.scanner)
        self.order = Order(self.scanner, self.links)
        self._backlinks = None
        self._schema = None

    @property
    def schema(self):
        if self._schema is None:
            self._schema = Config.load(self.scanner.path).schema
        return self._schema

    def inside(self, node):
        return self.selection.inside(node)

    def report(self, source, line, message):
        self.problems.setdefault(f'{self.selection.show(source)}:{line}: {message}')

    def nodes(self, folder=None):
        """Shown pages and folders in reading order, each with whether its text is built."""
        folder = folder or self.scanner.root
        yield folder, self.selection.selected(folder)
        for child in self.order.children(folder):
            if not self.selection.shows(child):
                continue
            if child.is_folder:
                yield from self.nodes(child)
            else:
                yield child, True

    def converter(self, node):
        return Converter(node, self.scanner, self.outdir, scope=self)

    def backlinks(self, node):
        """Built pages linking to node, in reading order, with headings links lead to: [(page, heading)]."""
        if not self.options.backlinks:
            return []
        if self._backlinks is None:
            self._backlinks = {}
            for source, body in self.nodes():
                if not body:
                    continue
                for target, heading, _ in self.links.of(source):
                    if target is source:
                        continue
                    heading = (heading or '').strip()
                    if heading and cebabize(heading) == cebabize(target.title):
                        heading = ''
                    entries = self._backlinks.setdefault(target, {})
                    entries.setdefault((source, cebabize(heading)), (source, heading))
        return list(self._backlinks.get(node, {}).values())

    def backlink_text(self, source, heading):
        return source.title + (self.SEP + heading if heading else '')

    def html_backlinks(self, node):
        """Backlinks as folded line of their count and titles unfolding into links."""
        backlinks = self.backlinks(node)
        if not backlinks:
            return ''
        texts = [html.escape(self.backlink_text(source, heading)) for source, heading in backlinks]
        links = [f'<a href="#{source.anchor}">{text}</a>' for (source, _), text in zip(backlinks, texts)]
        return (f'<details class="backlinks"><summary><b>Backlinks ({len(links)}):</b>'
                f'<span>{", ".join(texts)}</span></summary><div>{", ".join(links)}</div></details>')

    def md_backlinks(self, node):
        escape = lambda text: re.sub(r'([\\\[\]])', r'\\\1', text)
        links = [f'[{escape(self.backlink_text(source, heading))}](#{source.anchor})'
                 for source, heading in self.backlinks(node)]
        return f'Backlinks: {", ".join(links)}\n\n' if links else ''

    def issues_of(self, node):
        """What check reports for built page, split: (lines of its text: [(message, warning)], the rest)
        the rest is of front matter and of the page as a whole."""
        issues = self.issues.get(os.path.realpath(node.file), []) if node.file else []
        if not issues:
            return {}, []
        try:
            _, front, _, start = read_parts(node.file)
        except ValueError:
            return {}, []  # not UTF-8: the build reports it
        text, rest = {}, []
        for line, message, warning in issues:
            if front and line < start or not front and line == 1 and message.startswith(self.PAGE_ISSUES):
                rest.append((line, message, warning))
            else:
                text.setdefault(line, []).append((message, warning))
        return text, rest

    PAGE_ISSUES = ('orphan page', 'missing front matter key', 'not listed in')

    def html_problems(self, node, text, rest):
        """What check reports for the page as folded line of messages unfolding into links to where they are."""
        issues = sorted([(line, m, w) for line, items in text.items() for m, w in items] + rest)
        if not issues:
            return ''
        links = []
        for line, message, warning in issues:
            href = f'problem-{node.anchor}-{line}' if line in text else node.anchor
            kind = 'warning' if warning else 'problem'
            links.append(f'<a class="{kind}" href="#{href}">{line}: {html.escape(message)}</a>')
        label = 'Problems' if any(not w for _, _, w in issues) else 'Warnings'
        return (f'<details class="problems"><summary><b>{label} ({len(issues)}):</b>'
                f'<span>{html.escape(", ".join(m for _, m, _ in issues))}</span></summary>'
                f'<div>{"".join(links)}</div></details>')

    def html_front_matter(self, node, problem=False):
        """Front matter in schema order as folded line of values unfolding into a table of keys and values,
        none for title only."""
        if not self.options.front_matter or node.file is None:
            return ''
        items = self.schema.sort(read_front_matter(node.file), self.path(node))
        if not items:
            return ''
        text = lambda value: ', '.join(value) if isinstance(value, list) else value
        line = ' · '.join(text(value) for key, value in items if key != 'title' and text(value))
        if not line:
            return ''
        rows = ''.join(f'<tr><th>{html.escape(key)}</th><td>{html.escape(text(value))}</td></tr>'
                       for key, value in items)
        kind = ' problem' if problem else ''
        return (f'<details class="front-matter{kind}"><summary><span>{html.escape(line)}</span></summary>'
                f'<table>{rows}</table></details>')

    def path(self, node):
        return os.path.relpath(node.file, self.scanner.path).replace(os.sep, '/')

    def data(self, nodes):
        """What the page filters and counts by: front matter keys listing values in schema order,
        built pages by anchor with vault path, front matter, words as stats counts them and tokens."""
        pages = {}
        for node, body in nodes:
            if not body or node.file is None:
                continue
            _, _, text, _ = read_parts(node.file)
            pages[node.anchor] = {
                'path': self.path(node),
                'meta': dict(read_front_matter(node.file)),
                'words': Stats.words(text),
                'tokens': Stats.tokens(text),
                'problems': len(self.issues.get(os.path.realpath(node.file), [])),
            }
        data = {'facets': list(self.schema.facets().items()), 'pages': pages}
        return json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')

    def html(self, title):
        nodes = list(self.nodes())
        content = ''.join(self.html_node(node, body) for node, body in nodes)
        return self.render('uwiki.html', {
            'title':    html.escape(title),
            'content':  content,
            'data':     self.data(nodes),
            'style':    read_asset('uwiki.css'),
            'script':   read_asset('uwiki.js') + self.reload_script(),
        })

    def html_node(self, node, body):
        converter = self.converter(node)
        aside = self.html_backlinks(node)
        if body:
            text, rest = self.issues_of(node)
            converter.problems = text
            front = [line for line, _, _ in rest if line > 1]
            aside = self.html_problems(node, text, rest) + aside + self.html_front_matter(node, bool(front))
        return converter.html(body, aside)

    def reload_script(self):
        if not self.options.live_reload:
            return ''
        return read_asset('reload.js').replace('{build}', self.build_id)

    def md(self):
        return ''.join(self.converter(node).md(body) + self.md_backlinks(node) for node, body in self.nodes())

    @staticmethod
    def render(name, vars):
        return re.sub(r'\{(\w+)\}', lambda m: vars.get(m[1], m[0]), read_asset(name))

class Build:
    """Build of given folders and files into one HTML and one markdown file, as `uwiki build` takes options.

    Output is a folder, written `<title>.html` and `<title>.md` in it, or a file name:
    without extension both are written, with `.html` or `.md` only one.
    """

    KINDS = ('html', 'md')

    def __init__(self, paths, output=None, title=None, html=False, md=False, include=(), exclude=(), options=None):
        self.paths = list(paths)
        self.options = options or BuildOptions()
        self.include, self.exclude = list(include), list(exclude)
        self.filter = Filter(include, exclude)
        self.outputs, self.title = self.targets(self.paths, output, title, html, md)
        self.selection = None
        self.warnings = []
        self.build_id = ''

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

    def check(self, selection):
        """What check with the vault config reports for the built pages, by real path of page file."""
        options = CheckOptions.from_values(Config.load(selection.scanner.path).options('check', ()))
        checker = Checker(self.paths, self.include, self.exclude, options)
        try:
            checker.check()
        except (OSError, ValueError):
            return {}  # the build reports it
        return checker.issues

    def run(self):
        """Scans vault, renders and writes outputs; returns problems instead of writing if any."""
        selection = self.scan()
        outdir = os.path.dirname(os.path.abspath(next(iter(self.outputs.values()))))
        build_id = str(time.time_ns())
        issues = self.check(selection) if 'html' in self.outputs else {}
        builder = Builder(selection, outdir, self.options, build_id, issues)
        texts = {kind: builder.html(self.title) if kind == 'html' else builder.md() for kind in self.outputs}
        if builder.problems:
            return list(builder.problems)
        for kind, file in self.outputs.items():
            os.makedirs(os.path.dirname(os.path.abspath(file)), exist_ok=True)
            with open(file, 'w', encoding='utf-8') as f:
                f.write(texts[kind])
        self.build_id = build_id
        return []
