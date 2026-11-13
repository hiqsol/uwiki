"""Language server over stdio: links resolve as build and check resolve them.

Go to definition of wiki and markdown links, headings and items, hover shows what a link leads to,
completion of page names, aliases, headings and items, references of a page, heading or item,
outline of headings and items, diagnostics of `check` on open and save.
"""

import json
import os
import re
import sys
import traceback
from urllib.parse import quote, unquote, urlparse

from .check import Checker, CheckOptions
from .config import Config
from .convert import Converter
from .order import Links
from .vault import FRONT_MATTER, Filter, Scanner, Vaults, cebabize, read_aliases

HOVER_LINES = 12
SYMBOL_WIDTH = 60
PROBLEM = re.compile(r'(.*?):(\d+): (warning: )?(.*)')
OPEN_WIKILINK = re.compile(r'!?\[\[([^\[\]|]*)$')
WORD_END = re.compile(r'\w*')

def uri_path(uri):
    return os.path.abspath(unquote(urlparse(uri).path))

def path_uri(path):
    return 'file://' + quote(path)

def body(text):
    """Text after front matter and number of its first line, as read_text gives them for a file."""
    m = FRONT_MATTER.match(text)
    front = m[0] if m else ''
    return text[len(front):], front.count('\n') + 1

def indent(line):
    """Width of leading whitespace, tab counts as 4."""
    line = line.expandtabs(4)
    return len(line) - len(line.lstrip())

def section_key(heading):
    """Key of a section items are in, '' for the first list of the page."""
    return cebabize(heading) if heading else ''

class Server:
    """Answers one client: requests in order, the vault scanned again on save."""

    def __init__(self, input=None, output=None):
        self.input = input or sys.stdin.buffer
        self.output = output or sys.stdout.buffer
        self.root = None
        self.scanner = None
        self.links = None
        self.docs = {}  # path: text of open documents
        self.published = set()  # paths diagnostics were published for
        self.wide = False  # positions count code points, not UTF-16 units
        self.running = True

    # protocol

    def serve(self):
        while self.running:
            message = self.receive()
            if message is None:
                break
            self.dispatch(message)

    def receive(self):
        length = None
        while True:
            line = self.input.readline()
            if not line:
                return None
            line = line.strip()
            if not line:
                break
            name, _, value = line.decode('ascii').partition(':')
            if name.lower() == 'content-length':
                length = int(value)
        return json.loads(self.input.read(length)) if length else {}

    def send(self, message):
        data = json.dumps({'jsonrpc': '2.0', **message}).encode('utf-8')
        self.output.write(b'Content-Length: %d\r\n\r\n' % len(data) + data)
        self.output.flush()

    def notify(self, method, params):
        self.send({'method': method, 'params': params})

    def dispatch(self, message):
        method, id = message.get('method'), message.get('id')
        if method is None:
            return
        handler = getattr(self, 'on_' + method.replace('/', '_').replace('$', ''), None)
        try:
            result = handler(message.get('params') or {}) if handler else None
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            if id is not None:
                self.send({'id': id, 'error': {'code': -32603, 'message': str(e)}})
            return
        if id is not None:
            if handler is None:
                self.send({'id': id, 'error': {'code': -32601, 'message': f'unknown method {method}'}})
            else:
                self.send({'id': id, 'result': result})

    # lifecycle

    def on_initialize(self, params):
        folders = params.get('workspaceFolders') or []
        uri = folders[0]['uri'] if folders else params.get('rootUri')
        self.root = uri_path(uri) if uri else os.getcwd()
        encodings = params.get('capabilities', {}).get('general', {}).get('positionEncodings', [])
        self.wide = 'utf-32' in encodings
        self.scan()
        return {
            'capabilities': {
                'positionEncoding': 'utf-32' if self.wide else 'utf-16',
                'textDocumentSync': {'openClose': True, 'change': 1, 'save': {'includeText': False}},
                'definitionProvider': True,
                'hoverProvider': True,
                'referencesProvider': True,
                'documentSymbolProvider': True,
                'completionProvider': {'triggerCharacters': ['[', '#']},
            },
            'serverInfo': {'name': 'uwiki'},
        }

    def on_initialized(self, params):
        self.diagnose()

    def on_shutdown(self, params):
        return None

    def on_exit(self, params):
        self.running = False

    def on_textDocument_didOpen(self, params):
        doc = params['textDocument']
        path = uri_path(doc['uri'])
        self.docs[path] = doc['text']
        if self.node(path) is None and os.path.exists(path):
            self.scan()

    def on_textDocument_didChange(self, params):
        changes = params['contentChanges']
        if changes:
            self.docs[uri_path(params['textDocument']['uri'])] = changes[-1]['text']

    def on_textDocument_didClose(self, params):
        self.docs.pop(uri_path(params['textDocument']['uri']), None)

    def on_textDocument_didSave(self, params):
        self.scan()
        self.diagnose()

    def on_workspace_didChangeWatchedFiles(self, params):
        self.scan()
        self.diagnose()

    # vault

    def options(self):
        return Config.load(self.root).options('check', ())

    def scan(self):
        config = Config.load(self.root)
        options = config.options('check', ())
        self.scanner = Scanner(self.root, Filter(config.globs(options.get('include', [])),
                                                 config.globs(options.get('exclude', []))))
        self.scanner.scan()
        self.pages = self.scanner.pages()
        self.links = Links(self.scanner)

    def node(self, path):
        """Page or folder of a file, a loose page for one the scan does not know."""
        return self.pages.get(path)

    def source(self, path):
        """Page links of a file resolve from."""
        node = self.node(path) or Vaults.loose_page(self.scanner, path)
        return Converter(node, self.scanner)

    def text(self, path):
        """Text of a file as the editor has it, else as on disk."""
        if path in self.docs:
            return self.docs[path]
        try:
            with open(path, encoding='utf-8') as f:
                return f.read()
        except (OSError, UnicodeDecodeError):
            return ''

    def lines(self, path):
        return self.text(path).splitlines()

    # positions

    def column(self, line, index):
        """Position column of a string index."""
        return index if self.wide else len(line[:index].encode('utf-16-le')) // 2

    def index(self, line, column):
        """String index of a position column."""
        if self.wide:
            return column
        units = 0
        for i, c in enumerate(line):
            if units >= column:
                return i
            units += 2 if ord(c) > 0xFFFF else 1
        return len(line)

    def range(self, lines, n, start=0, end=None):
        line = lines[n] if n < len(lines) else ''
        end = len(line) if end is None else end
        return {'start': {'line': n, 'character': self.column(line, start)},
                'end': {'line': n, 'character': self.column(line, end)}}

    def location(self, path, n, start=0, end=None):
        return {'uri': path_uri(path), 'range': self.range(self.lines(path), n, start, end)}

    def position(self, params):
        """Path, lines, line number and string index of a request position."""
        path = uri_path(params['textDocument']['uri'])
        lines = self.lines(path)
        n = params['position']['line']
        line = lines[n] if n < len(lines) else ''
        return path, lines, n, self.index(line, params['position']['character'])

    # links

    @staticmethod
    def code_spans(line):
        return [m.span() for m in Converter.CODE.finditer(line)]

    def link_at(self, line, i):
        """Link around string index: ('wiki', text) or ('md', href), with its span, else None;
        a wiki link takes the word ending glued to it, the s of `[[Card]]s`."""
        code = self.code_spans(line)
        inside = lambda m: any(a <= m.start() < b for a, b in code)
        for m in Converter.WIKILINK.finditer(line):
            end = WORD_END.match(line, m.end()).end()
            if m.start() <= i < end and not inside(m):
                return 'wiki', m[2], (m.start(), end)
        for m in Converter.MD_LINK.finditer(line):
            if not m[1] and m.start() <= i < m.end():
                return 'md', m[3], m.span()
        return None

    def target(self, path, kind, text):
        """Node a link leads to, heading and item in it, None if it leads nowhere in the vault."""
        conv = self.source(path)
        if kind == 'wiki':
            name, heading, item, _ = conv.parse_target(text)
            node, aliased = self.scanner.lookup(name, conv.source.path) if name else (conv.page, False)
            if node is None:
                return None
            found = aliased and not heading and not item and node.source and conv.alias_item(node.source, name)
            if found:
                item, heading = found
            heading = '' if heading.startswith('^') else heading
            if item:
                heading = conv.title_section(node, heading)
            return node, heading, item
        if not conv.is_local(text):
            return None
        node, heading = conv.resolve_href(text)
        if node is None:
            return None
        fragment = unquote(text).partition('#')[2]
        if Converter.ITEM.fullmatch(fragment):
            return node, '', fragment
        return node, heading or '', ''

    def file(self, node):
        source = node.source
        return source.fullpath if source is not None else None

    def body_of(self, file):
        return body(self.text(file))

    def item_lines(self, file):
        """Line index in file, number path and section keys of every linkable item."""
        text, start = self.body_of(file)
        return [(start - 1 + i, path, [section_key(k) for k in keys])
                for i, path, keys in Converter.list_items(text)]

    def heading_lines(self, file):
        """Line index in file, level and text of every heading."""
        text, start = self.body_of(file)
        return [(start - 1 + i, len(m[1]), m[2]) for i, (_, m) in enumerate(Converter.headings(text)) if m]

    def find(self, node, heading, item):
        """File and line index a link target is at, line 0 for a page, None if the page has no text."""
        file = self.file(node)
        if file is None:
            return None
        if item:
            key = section_key(heading)
            return file, next((n for n, path, keys in self.item_lines(file) if path == item and key in keys), 0)
        if heading:
            key = cebabize(heading)
            return file, next((n for n, _, text in self.heading_lines(file) if cebabize(text) == key), 0)
        return file, 0

    # requests

    def on_textDocument_definition(self, params):
        path, lines, n, i = self.position(params)
        link = self.link_at(lines[n] if n < len(lines) else '', i)
        target = link and self.target(path, link[0], link[1])
        found = target and self.find(*target)
        if not found:
            return None
        file, line = found
        return self.location(file, line, 0, 0)

    def on_textDocument_hover(self, params):
        path, lines, n, i = self.position(params)
        link = self.link_at(lines[n] if n < len(lines) else '', i)
        target = link and self.target(path, link[0], link[1])
        found = target and self.find(*target)
        if not found:
            return None
        file, line = found
        node, heading, item = target
        text = self.lines(file)
        if item:
            block = self.item_block(text, line)
        elif heading:
            block = text[line:line + HOVER_LINES]
        else:
            first = self.body_of(file)[1] - 1
            block = text[first:first + HOVER_LINES]
        name = link[0] == 'wiki' and Converter.parse_target(link[1])[0]
        title = node.page.title if name and Converter.names_folder_page(node, name) else node.title
        title = '#'.join([title, *filter(None, [heading]), item]) if item else title
        return {'contents': {'kind': 'markdown', 'value': f'**{title}**\n\n' + '\n'.join(block).strip()},
                'range': self.range(lines, n, *link[2])}

    @staticmethod
    def item_block(lines, n):
        """Item line, its continuation and its nested items."""
        block = [lines[n]]
        for line in lines[n + 1:]:
            if not line.strip() or indent(line) <= indent(lines[n]):
                break
            block.append(line)
        return block

    def on_textDocument_completion(self, params):
        path, lines, n, i = self.position(params)
        before = (lines[n] if n < len(lines) else '')[:i]
        m = OPEN_WIKILINK.search(before)
        if not m:
            return None
        typed = m[1]
        start = i - len(typed)
        name, sep, rest = typed.partition('#')
        if not sep:
            return self.name_items(lines, n, start, i, path)
        conv = self.source(path)
        node = self.scanner.resolve(name, conv.source.path) if name.strip() else conv.page
        if node is None or self.file(node) is None:
            return []
        heading, sep2, _ = rest.rpartition('#')
        start = i - len(rest) + (len(heading) + 1 if sep2 else 0)
        return self.anchor_items(node, heading if sep2 else None, lines, n, start, i)

    def edit(self, lines, n, start, end, text):
        return {'range': self.range(lines, n, start, end), 'newText': text}

    def name_items(self, lines, n, start, end, path):
        """Page and folder names, path where names clash, then aliases."""
        nodes = [node for node in self.pages.values() if node is not self.scanner.root]
        nodes += [node for node in self.folders() if node.page is None]
        counts = {}
        for node in nodes:
            counts[node.name.lower()] = counts.get(node.name.lower(), 0) + 1
        res = []
        for node in nodes:
            label = node.name if counts[node.name.lower()] == 1 else node.path.strip('/')
            res.append({'label': label, 'kind': 19 if node.is_folder and not node.page else 17,
                        'detail': self.shown(node), 'textEdit': self.edit(lines, n, start, end, label)})
        for alias, entries in self.scanner.aliases.items():
            for _, node in entries:
                name = next((a for a in read_aliases(node.file) if a.lower() == alias), alias)
                res.append({'label': name, 'kind': 18, 'detail': f'alias of {self.shown(node)}',
                            'textEdit': self.edit(lines, n, start, end, name)})
        return res

    def folders(self):
        res, todo = [], [self.scanner.root]
        for folder in todo:
            for child in folder.children.values():
                if child.is_folder:
                    res.append(child)
                    todo.append(child)
        return res

    def shown(self, node):
        return os.path.relpath(node.file or node.fullpath, self.root)

    def anchor_items(self, node, heading, lines, n, start, end):
        """Headings and items of a page after `#`, items of a section after `#Heading#`."""
        file = self.file(node)
        text = self.lines(file)
        res = []
        if heading is None:
            for line, level, title in self.heading_lines(file):
                res.append({'label': title, 'kind': 18, 'detail': '#' * level,
                            'sortText': f'{line:06}', 'textEdit': self.edit(lines, n, start, end, title)})
        key = section_key(heading)
        for line, path, keys in self.item_lines(file):
            if key in keys:
                words = text[line].strip().split(' ', 1)[-1]
                res.append({'label': path, 'kind': 12, 'detail': words, 'filterText': f'{path} {words}',
                            'sortText': f'{line:06}', 'textEdit': self.edit(lines, n, start, end, path)})
        return sorted(res, key=lambda item: item['sortText'])

    def on_textDocument_references(self, params):
        path, lines, n, i = self.position(params)
        line = lines[n] if n < len(lines) else ''
        link = self.link_at(line, i)
        target = link and self.target(path, link[0], link[1])
        if not target:
            node = self.node(path)
            if node is None:
                return []
            target = node, '', ''
            item = next(((p, keys) for l, p, keys in self.item_lines(path) if l == n), None)
            heading = next((t for l, _, t in self.heading_lines(path) if l == n), None)
            if item:
                target = node, item[1][-1], item[0]
            elif heading:
                target = node, heading, ''
        return self.references(*target)

    def references(self, node, heading, item):
        """Lines linking to a page, to a heading of it or to an item, the latter in any section key it has."""
        keys = None
        if item:
            file = self.file(node)
            keys = next((k for _, p, k in self.item_lines(file) if p == item and section_key(heading) in k), [])
        res = []
        for page in sorted(set(self.pages.values()), key=lambda p: p.source.fullpath if p.source else ''):
            for target, linked, line in self.links.of(page):
                if target is not node or not self.leads(linked or '', heading, item, keys):
                    continue
                res.append(self.location(page.source.fullpath, line - 1))
        return res

    @staticmethod
    def leads(linked, heading, item, keys):
        """Whether a link to heading or item text `Heading › 3`, `3` or `Heading` leads where asked."""
        if not heading and not item:
            return True
        section, _, number = linked.rpartition(' › ')
        if not Converter.ITEM.fullmatch(number):
            section, number = linked, ''
        if item:
            return number == item and section_key(section) in keys
        return section_key(section) == section_key(heading)

    def on_textDocument_documentSymbol(self, params):
        """Headings, the items links can name nested under them."""
        path = uri_path(params['textDocument']['uri'])
        lines = self.lines(path)
        root = {'children': []}
        stack = [(0, root)]
        items = {n: p for n, p, _ in self.item_lines(path)}
        headings = {n: (level, title) for n, level, title in self.heading_lines(path)}
        parents = {}
        for n in sorted({*items, *headings}):
            if n in headings:
                level, title = headings[n]
                symbol = self.symbol(title, 15, lines, n)
                while len(stack) > 1 and stack[-1][0] >= level:
                    stack.pop()
                stack[-1][1]['children'].append(symbol)
                stack.append((level, symbol))
                parents = {}
            else:
                number = items[n]
                words = lines[n].strip().split(' ', 1)[-1]
                symbol = self.symbol(f'{number} {words}'[:SYMBOL_WIDTH], 16, lines, n)
                parent = parents.get(number.rpartition('.')[0], stack[-1][1])
                parent['children'].append(symbol)
                parents[number] = symbol
        return root['children']

    def symbol(self, name, kind, lines, n):
        r = self.range(lines, n)
        return {'name': name or ' ', 'kind': kind, 'range': r, 'selectionRange': r, 'children': []}

    # diagnostics

    def check_options(self):
        return CheckOptions.from_values(self.options())

    def diagnose(self):
        """Publishes check problems of every page, clears them where none are left."""
        config = Config.load(self.root)
        options = config.options('check', ())
        checker = Checker([self.root], config.globs(options.get('include', [])),
                          config.globs(options.get('exclude', [])), CheckOptions.from_values(options))
        found = {}
        for problem in checker.check() + checker.warnings:
            m = PROBLEM.fullmatch(problem)
            if not m:
                continue
            found.setdefault(os.path.normpath(os.path.join(self.root, m[1])), []).append((int(m[2]) - 1, bool(m[3]), m[4]))
        for file in self.published - set(found):
            self.notify('textDocument/publishDiagnostics', {'uri': path_uri(file), 'diagnostics': []})
        for file, problems in found.items():
            lines = self.lines(file)
            self.notify('textDocument/publishDiagnostics', {
                'uri': path_uri(file),
                'diagnostics': [self.diagnostic(lines, n, warning, message) for n, warning, message in problems],
            })
        self.published = set(found)

    def diagnostic(self, lines, n, warning, message):
        """Diagnostic on what the message names in its line, else on the whole line."""
        line = lines[n] if 0 <= n < len(lines) else ''
        named = message.partition(': ')[2]
        start = line.find(named) if named else -1
        span = (start, start + len(named)) if start >= 0 else (0, len(line))
        return {'range': self.range(lines, max(n, 0), *span), 'severity': 2 if warning else 1,
                'source': 'uwiki', 'message': message}
