"""Vault model: pages, folders and Obsidian-like link resolution."""

import functools
import os
import posixpath
import re
from pathlib import Path

FRONT_MATTER = re.compile(r'\A---[ \t]*\r?\n.*?^(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)', re.DOTALL | re.MULTILINE)
TITLE = re.compile(r'\A(\s*)(#{1,6})[ \t]+(.*?)[ \t]*(?:\r?\n|\Z)')

_files = {}  # path: (mtime and size, text, front matter, text after it, number of its first line)

def read_parts(path):
    """Text of file, its front matter, text after it and number of its first line.

    Read once while the file stays the same, every command asks for a page many times.
    """
    st = os.stat(path)
    stamp = st.st_mtime_ns, st.st_size
    cached = _files.get(path)
    if cached is None or cached[0] != stamp:
        with open(path, encoding='utf-8') as f:
            text = f.read()
        m = FRONT_MATTER.match(text)
        front = m[0] if m else ''
        cached = _files[path] = stamp, text, front, text[len(front):], front.count('\n') + 1
    return cached[1:]

def read_text(path):
    """Returns file text without front matter and number of its first line."""
    try:
        return read_parts(path)[2:]
    except UnicodeDecodeError as e:
        raise ValueError(f'Error reading {path}') from e

def read_front(path):
    """Front matter of file with its `---` lines, empty if none or unreadable."""
    try:
        return read_parts(path)[1]
    except (OSError, TypeError, UnicodeDecodeError):
        return ''

# files titled by their name whatever front matter or heading they have: names tools look for
NAME_TITLED = ('AGENTS.md',)

def read_title(path):
    """Front matter title, else heading the file starts with, if any; file name of NAME_TITLED files."""
    if path and os.path.basename(path) in NAME_TITLED:
        return os.path.basename(path)
    title = front_matter_value(read_front(path), 'title')
    if title:
        return title
    try:
        heading = TITLE.match(read_parts(path)[2])
    except (OSError, TypeError, UnicodeDecodeError):
        return None
    return heading[3] if heading else None

def read_description(path):
    return front_matter_value(read_front(path), 'description')

def read_file(path):
    try:
        return read_parts(path)[0]
    except (OSError, TypeError, UnicodeDecodeError):
        return ''

def front_matter_value(front, key):
    """Top level scalar of front matter: plain, quoted, folded or literal, lines joined; None if missing."""
    lines = front.splitlines()
    for i, line in enumerate(lines):
        m = re.match(rf'{re.escape(key)}:(?:[ \t]+(.*?))?[ \t]*$', line)
        if not m:
            continue
        value = m[1] or ''
        more = []
        for line in lines[i + 1:]:
            if line.strip() and not line[0].isspace():
                break
            more.append(line.strip())
        if value[:1] in ('>', '|'):
            return ('\n' if value[0] == '|' else ' ').join(more).strip() or None
        value = ' '.join([value, *filter(None, more)])
        if value[:1] in ('"', "'") and value[-1:] == value[0] and len(value) > 1:
            return value[1:-1].replace("''", "'") if value[0] == "'" else value[1:-1]
        return re.sub(r'\s+#.*$', '', value).strip() or None
    return None

def read_front_matter(path):
    """Top level front matter of file as (key, value) pairs, see front_matter_items."""
    return front_matter_items(read_front(path))

def read_aliases(path):
    """Front matter `aliases` (or `alias`) of file, a list or one text."""
    res = []
    for key, value in read_front_matter(path) if path else []:
        if key in ('aliases', 'alias'):
            res += [v for v in (value if isinstance(value, list) else [value]) if v.strip()]
    return [v.strip() for v in res]

def front_matter_items(front):
    """Top level keys of front matter in order with values: scalar as text, list as list of texts.

    Lists are inline `[a, b]` or `- a` lines, nested keys give `key: value` texts.
    """
    lines = front.splitlines()[1:-1]
    res = []
    for i, line in enumerate(lines):
        m = re.match(r'([^\s#:][^:]*?):(?:[ \t]+(.*?))?[ \t]*$', line)
        if not m:
            continue
        key, value = m[1].strip('\'"'), (m[2] or '').strip()
        if value[:1] == '[' and value[-1:] == ']':
            res.append((key, [unquote_scalar(v) for v in split_flow(value[1:-1])]))
            continue
        if not value:
            nested = []
            for line in lines[i + 1:]:
                if line.strip() and not line[0].isspace() and not line.startswith('- '):
                    break
                item = line.strip()
                if item and not item.startswith('#'):
                    nested.append(unquote_scalar(item[2:]) if item.startswith('- ') or item == '-' else item)
            if nested:
                res.append((key, nested))
                continue
        res.append((key, front_matter_value(front, m[1]) or ''))
    return res

def front_matter_tree(front):
    """Front matter as a map: front_matter_items values, maps and lists of maps nested as such.

    Maps are `{a: 1, b: 2}` or indented `a: 1` lines, lists of maps `- a: 1` items with keys under them.
    """
    lines = front.splitlines()[1:-1]
    res = {}
    for key, value in front_matter_items(front):
        res[key] = nested_value(lines, key, value)
    return res

def nested_value(lines, key, value):
    """Value of top level key as a map or a list of maps when it is one, else value as given."""
    pattern = re.compile(rf'[\'"]?{re.escape(key)}[\'"]?:(?:[ \t]+(.*?))?[ \t]*$')
    for i, line in enumerate(lines):
        m = pattern.match(line)
        if not m:
            continue
        inline = (m[1] or '').strip()
        if inline[:1] == '{' and inline[-1:] == '}':
            return flow_map(inline)
        if inline:
            return value
        block = []
        for line in lines[i + 1:]:
            if line.strip() and not line[0].isspace() and not line.startswith('- '):
                break
            if line.strip() and not line.strip().startswith('#'):
                block.append((len(line) - len(line.lstrip()), line.strip()))
        parsed = block_value(block)
        return parsed if isinstance(parsed, dict) or isinstance(parsed, list) and any(
            isinstance(v, dict) for v in parsed) else value
    return value

def flow_map(text):
    res = {}
    for item in split_flow(text[1:-1]):
        key, _, value = item.partition(':')
        res[key.strip().strip('\'"')] = scalar(value)
    return res

def scalar(text):
    """Inline value: flow list or map, else unquoted text."""
    text = text.strip()
    if text[:1] == '[' and text[-1:] == ']':
        return [unquote_scalar(v) for v in split_flow(text[1:-1])]
    if text[:1] == '{' and text[-1:] == '}':
        return flow_map(text)
    return unquote_scalar(text)

def block_value(block):
    """Map or list of indented (indent, text) lines, of the lines at the first line's indent."""
    if not block:
        return ''
    indent = block[0][0]
    if block[0][1].startswith('-'):
        items = []
        for level, text in block:
            if level == indent and text.startswith('-'):
                items.append([(level + 2, text[1:].strip())] if text[1:].strip() else [])
            elif items:
                items[-1].append((level, text))
        return [block_value(item) if item and KEY.match(item[0][1]) else
                scalar(item[0][1]) if item else '' for item in items]
    res = {}
    for n, (level, text) in enumerate(block):
        m = KEY.match(text)
        if level != indent or not m:
            continue
        if m[2]:
            res[m[1]] = scalar(m[2])
        else:
            nested = []
            for level2, text2 in block[n + 1:]:
                if level2 <= indent and not (level2 == indent and text2.startswith('-')):
                    break
                nested.append((level2, text2))
            res[m[1]] = block_value(nested)
    return res

KEY = re.compile(r'[\'"]?([^\s#:\'"][^:]*?)[\'"]?:(?:[ \t]+(.*?))?[ \t]*$')

def split_flow(text):
    """Splits `a, "b, c", d` by commas outside quotes."""
    items, cur, quote = [], '', None
    for c in text:
        if quote:
            quote = None if c == quote else quote
        elif c in '"\'':
            quote = c
        elif c == ',':
            items.append(cur)
            cur = ''
            continue
        cur += c
    items.append(cur)
    return [item.strip() for item in items if item.strip()]

def unquote_scalar(value):
    value = value.strip()
    if len(value) > 1 and value[0] in '"\'' and value[-1] == value[0]:
        return value[1:-1]
    return re.sub(r'\s+#.*$', '', value)

@functools.lru_cache(maxsize=1 << 16)
def titleize(name):
    words = camel_split(name, r'[\s_-]+')
    if not words:
        return name
    return ' '.join(w[0].upper() + w[1:] for w in words)

# ids of the HTML page template, no page anchor takes them; ones starting with _ need no listing,
# no anchor has _ as cebabize splits words at it
TEMPLATE_IDS = ('top', 'home', 'smaller', 'larger', 'menu', 'sidebar', 'search', 'query', 'clear', 'stats', 'counts',
                'problems', 'facets', 'fold', 'toc', 'resize', 'data')

@functools.lru_cache(maxsize=1 << 16)
def cebabize(name):
    """Anchor of name, compared for every link and heading, so cached."""
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
        self.default_title = titleize(name)
        self._title = None
        self.anchor = cebabize(name)

    @property
    def source(self):
        """Page whose text it is: itself, folder page for a folder, None for a folder without one."""
        return self

    @property
    def file(self):
        return self.fullpath

    @property
    def title(self):
        """Front matter title or leading heading of the page, else its name."""
        if self._title is None:
            self._title = read_title(self.file) or self.default_title
        return self._title

    def __repr__(self):
        return f'{type(self).__name__}(name={self.name}, title={self.title}, path={self.path})'

class Folder(Page):
    def __init__(self, folder, name, path, fullpath):
        super().__init__(folder, name, path, fullpath)
        self.is_folder = True
        self.children = {}
        self.page = None

    @property
    def source(self):
        return self.page

    @property
    def file(self):
        return self.page.fullpath if self.page else None

    def child(self, is_folder, name, path, fullpath):
        res = (Folder if is_folder else Page)(self, name, path, fullpath)
        res.depth = self.depth + 1
        if not is_folder and self.is_index(name) and (
            self.page is None or self.is_readme(name) and not self.is_readme(self.page.name)
        ):
            if self.page:
                self.children[self.page.name + '.md'] = self.page
            self.page = res
        else:
            # page `Name.md` and folder `Name/` can sit side by side
            self.children[name if is_folder else name + '.md'] = res
        return res

    def is_index(self, name):
        name = name.lower()
        return name in [self.name.lower(), self.singularize(self.name.lower()), 'index', 'readme']

    @staticmethod
    def is_readme(name):
        return name.lower() == 'readme'

    def shadowed_index(self):
        """Index page that README took folder page place from, if any."""
        if self.page and self.is_readme(self.page.name):
            return next((c for c in self.children.values() if not c.is_folder and c.name.lower() == 'index'), None)
        return None

    def is_empty(self):
        return self.page is None and not self.children

    def singularize(self, name):
        if name.endswith('ies'):
            return name[:-3] + 'y'
        if name.endswith('s'):
            return name[:-1]
        return name

class Filter:
    """Takes vault paths: skip list and excludes drop them, includes take them back.

    Glob with `/` matches path from vault root, without it any path segment, like gitignore;
    matching folder matches everything in it. `{a,b}` matches either, as in shells and editorconfig.
    """
    SKIP = ('.*', 'node_modules', 'vendor')

    def __init__(self, include=(), exclude=()):
        self.include = [self.compile(p) for p in include]
        self.include_prefixes = [self.prefix(p) for p in include]
        self.drop = [self.compile(p) for p in (*self.SKIP, *exclude)]

    @classmethod
    def compile(cls, glob):
        return re.compile('|'.join(f'(?:{cls.pattern(one)})' for one in cls.expand(glob)))

    @classmethod
    def expand(cls, glob):
        """Globs the `{a,b}` alternatives of glob stand for, glob itself when it has none or one is unclosed."""
        start = glob.find('{')
        if start < 0:
            return [glob]
        depth, parts, last = 0, [], start + 1
        for i in range(start, len(glob)):
            if glob[i] == '{':
                depth += 1
            elif glob[i] == ',' and depth == 1:
                parts.append(glob[last:i])
                last = i + 1
            elif glob[i] == '}':
                depth -= 1
                if not depth:
                    parts.append(glob[last:i])
                    tails = cls.expand(glob[i + 1:])
                    return [glob[:start] + one + tail for part in parts for one in cls.expand(part) for tail in tails]
        return [glob]

    @staticmethod
    def pattern(glob):
        glob = glob.strip('/')
        res = '' if '/' in glob else '(?:.*/)?'
        i = 0
        while i < len(glob):
            if glob.startswith('**/', i):
                res += '(?:.*/)?'
                i += 3
            elif glob.startswith('**', i):
                res += '.*'
                i += 2
            else:
                res += {'*': '[^/]*', '?': '[^/]'}.get(glob[i], re.escape(glob[i]))
                i += 1
        return res + '(?:/.*)?'

    @staticmethod
    def prefix(glob):
        """Literal start of anchored glob, empty for one matching anywhere."""
        glob = glob.strip('/')
        return re.split(r'[*?{]', glob)[0] if '/' in glob else ''

    def takes(self, path):
        if any(p.fullmatch(path) for p in self.include):
            return True
        return not any(p.fullmatch(path) for p in self.drop)

    def enters(self, path):
        """Folder is scanned when taken or an include can take something in it."""
        path += '/'
        return self.takes(path[:-1]) or any(p.startswith(path) or path.startswith(p) for p in self.include_prefixes)

class Scanner:
    def __init__(self, path, filter=None):
        self.path = path
        self.root = Folder(None, Path(path).name, '', self.path)
        self.root.default_title = ''
        self.root.anchor = 'root'
        self.filter = filter or Filter()
        self.targets = {}
        self.attachments = {}
        self.symlinks = []
        self.warnings = []
        self._aliases = None
        self._lookups = {}  # (name, source): lookup result, a build looks the same links up 50k times

    def scan(self, links=True):
        """Finds pages and attachments, then link targets and anchors unless only files are wanted."""
        self._scan_dir(self.root)
        if links:
            self._index(self.root)
            self._alias_symlinks()
            self._assign_anchors()

    @classmethod
    def from_files(cls, path, files):
        """Vault of given vault relative files as if scanned, for files not on disk yet, e.g. after a move."""
        scanner = cls(path)
        tree = {}
        for file in files:
            *folders, name = file.split('/')
            node = tree
            for folder in folders:
                node = node.setdefault(folder, {})
            node[name] = None
        def build(folder, tree):
            for name in sorted(tree):
                fullpath = os.path.join(folder.fullpath, name)
                rel = fullpath[len(scanner.path):]
                if tree[name] is not None:
                    item = folder.child(True, name, rel, fullpath)
                    build(item, tree[name])
                    if item.is_empty():
                        del folder.children[item.name]
                elif name.endswith('.md'):
                    folder.child(False, Path(name).stem, rel[:-3], fullpath)
                else:
                    scanner.attachments.setdefault(name.lower(), []).append(fullpath)
        build(scanner.root, tree)
        scanner._index(scanner.root)
        scanner._assign_anchors()
        return scanner

    def file_paths(self, pages=True):
        """Full paths of pages and attachments, or of attachments only."""
        return [*(self.pages() if pages else ()), *(f for files in self.attachments.values() for f in files)]

    def files(self):
        """Vault relative paths of pages and attachments."""
        return sorted(os.path.relpath(f, self.path).replace(os.sep, '/') for f in self.file_paths())

    def _scan_dir(self, folder):
        base = folder.fullpath
        o = sorted(os.scandir(base), key=lambda e: e.name)
        for entry in o:
            fullpath = os.path.join(base, entry.name)
            path = fullpath[len(self.path):]
            if entry.is_symlink() and self.inside(os.path.realpath(fullpath)) and (
                    entry.is_dir() or entry.name.endswith('.md')):
                if self.filter.takes(path.lstrip('/')):
                    self.symlinks.append((os.path.splitext(path)[0] if entry.is_file() else path,
                                          os.path.realpath(fullpath)))
                continue
            if entry.is_dir():
                if not self.filter.enters(path.lstrip('/')):
                    continue
                item = folder.child(True, entry.name, path, fullpath)
                self._scan_dir(item)
                if item.is_empty():
                    del folder.children[item.name]
            elif not self.filter.takes(path.lstrip('/')):
                continue
            elif entry.name.endswith('.md'):
                folder.child(False, Path(entry.name).stem, path[:-3], fullpath)
            else:
                self.attachments.setdefault(entry.name.lower(), []).append(fullpath)
        index = folder.shadowed_index()
        if index:
            self.warnings.append(f'{index.path.lstrip("/")}.md: {self.shadowed_message(folder)}')

    @staticmethod
    def shadowed_message(folder):
        return f'both index.md and {folder.page.name}.md in folder, {folder.page.name}.md is folder page'

    def inside(self, path):
        return path.startswith(os.path.join(os.path.realpath(self.path), ''))

    def _alias_symlinks(self):
        """Symlinks to vault pages and folders are skipped, links through them resolve to what they point at."""
        pages = {os.path.realpath(file): node for file, node in self.pages().items()}
        targets = [entry for entries in self.targets.values() for entry in entries]
        root = os.path.realpath(self.path)
        for path, real in self.symlinks:
            if real in pages:
                self._add_target(path, pages[real])
            elif os.path.isdir(real):
                prefix = '/' + os.path.relpath(real, root).replace(os.sep, '/').lower()
                for target, node in targets:
                    if target == prefix or target.startswith(prefix + '/'):
                        self._add_target(path + target[len(prefix):], node)

    def pages(self):
        """Pages by file path, folder pages give folders."""
        res = {}
        def collect(folder):
            if folder.page:
                res[folder.page.fullpath] = folder
            for child in folder.children.values():
                if child.is_folder:
                    collect(child)
                else:
                    res[child.fullpath] = child
        collect(self.root)
        return res

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
        used = {'root', *TEMPLATE_IDS}
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

    @property
    def aliases(self):
        """Alias in lower case: [(path, node)] of pages and folder pages with it in front matter `aliases`."""
        if self._aliases is None:
            self._aliases = {}
            for file, node in self.pages().items():
                for alias in read_aliases(file):
                    entries = self._aliases.setdefault(alias.lower(), [])
                    if node not in (n for _, n in entries):
                        entries.append((node.path.lower(), node))
        return self._aliases

    @staticmethod
    def link_name(name):
        name = name.strip().strip('/').lower()
        return name[:-3] if name.endswith('.md') else name

    def named(self, name, source=''):
        """Targets by name or path, best first: pages before folders without folder page, near ones, short paths."""
        near = str(Path(source).parent).lower().rstrip('/') + '/'
        name = self.link_name(name)
        candidates = sorted(
            (node.is_folder and not node.page, not path.startswith(near), path.count('/'), path, node)
            for path, node in self.targets.get(Path(name).name, [])
            if path.endswith('/' + name)
        ) if name else []
        return [(c[0], c[4]) for c in candidates]

    def alias(self, name, source=''):
        """Page with given alias, nearest to source if several, None if none."""
        name = self.link_name(name)
        if not name or '/' in name:
            return None
        near = str(Path(source).parent).lower().rstrip('/') + '/'
        candidates = [(not path.startswith(near), path.count('/'), path, node)
                      for path, node in self.aliases.get(name, [])]
        return min(candidates, key=lambda c: c[:3])[3] if candidates else None

    def lookup(self, name, source=''):
        """Link target by name or path like Obsidian finds it, and whether it is found by its alias.

        Prefers pages to aliases of pages, then to folders without folder page, as Obsidian links no folders,
        then targets near the source page, then shortest path.
        """
        key = (name, source)
        found = self._lookups.get(key)
        if found is None:
            found = self._lookups[key] = self._lookup(name, source)
        return found

    def _lookup(self, name, source):
        named = self.named(name, source)
        if not named or named[0][0]:
            aliased = self.alias(name, source)
            if aliased is not None:
                return aliased, True
        return (named[0][1] if named else None), False

    def resolve(self, name, source=''):
        """Link target by name or path, see lookup."""
        return self.lookup(name, source)[0]

    @staticmethod
    def vault_path(path, source=''):
        """Vault relative path of a path relative to the source page, None if it leads out of the vault."""
        path = posixpath.normpath(posixpath.join(posixpath.dirname(source).lstrip('/'), path))
        return None if path.startswith('..') else path

    def resolve_path(self, path, source=''):
        """Finds link target by path relative to the source page, as markdown links give it."""
        path = self.vault_path(path, source)
        if path is None:
            return None
        path = '/' + path.lower()
        if path.endswith('.md'):
            path = path[:-3]
        return next((node for p, node in self.targets.get(Path(path).name, []) if p == path), None)


class Vaults:
    """Markdown files under given paths, each with the vault it links in, paths in one vault share it."""

    def __init__(self, paths, filter=None):
        self.paths = paths
        self.filter = filter
        self.vaults = {}

    @staticmethod
    def common(paths):
        """Folder all given paths share."""
        return os.path.commonpath([p if os.path.isdir(p) else os.path.dirname(p) for p in map(os.path.abspath, paths)])

    def files(self):
        """Yields scanner, page and path to show of every file once, folder pages give folders."""
        seen = set()
        common = self.common(self.paths)
        for arg in self.paths:
            path = os.path.abspath(arg)
            scanner, pages = self.vault(self.vault_root(path, common))
            if os.path.isdir(path):
                files = sorted((p for p in pages if p.startswith(os.path.join(path, ''))), key=Path)
            else:
                files = [path]
            for file in files:
                if file not in seen:
                    seen.add(file)
                    shown = os.path.join(arg, os.path.relpath(file, path)) if file != path else arg
                    yield scanner, pages.get(file) or self.loose_page(scanner, file), shown

    @staticmethod
    def vault_root(path, common):
        """Nearest folder with `.obsidian`, else common folder of all given paths."""
        start = Path(path if os.path.isdir(path) else os.path.dirname(path))
        for folder in [start, *start.parents]:
            if (folder / '.obsidian').is_dir():
                return str(folder)
        return common

    def vault(self, root):
        """Scanned vault and its pages by file path, folder pages give folders."""
        if root not in self.vaults:
            scanner = Scanner(root, self.filter)
            scanner.scan()
            pages = scanner.pages()
            self.vaults[root] = scanner, pages
        return self.vaults[root]

    @staticmethod
    def loose_page(scanner, file):
        """Page for a file scanner skipped, e.g. hidden one."""
        return Page(None, Path(file).stem, os.path.splitext(file[len(scanner.path):])[0], file)


class Selection:
    """Pages under given paths in the one vault they share, as build and llms take them.

    Vault root is found as Vaults does, pages keep their folders from it,
    folders on the way to selected pages are shown by their titles only.
    """

    def __init__(self, paths, filter=None):
        self.paths = [os.path.abspath(p) for p in paths]
        self.vaults = Vaults(paths, filter)
        common = Vaults.common(self.paths)
        roots = {Vaults.vault_root(p, common) for p in self.paths}
        if len(roots) > 1:
            raise ValueError('paths are in different vaults: ' + ', '.join(sorted(roots)))
        self.root = roots.pop()
        self.scanner, pages = self.vaults.vault(self.root)
        nodes = set(pages.values())
        self.shown = {}  # selected node: path to show
        for scanner, page, shown in self.vaults.files():
            if page in nodes:
                self.shown[page] = shown
        self.common = self.folder(common)
        self.shown_root = next((arg for arg, p in zip(paths, self.paths) if p == self.root),
                               os.path.relpath(self.root))
        self.ancestors = set()
        for node in self.shown:
            folder = node.folder
            while folder and folder not in self.ancestors:
                self.ancestors.add(folder)
                folder = folder.folder

    def folder(self, path):
        """Vault folder at given path, None if it is no folder of the vault."""
        node = self.scanner.root
        for name in Path(os.path.relpath(path, self.root)).parts:
            node = node.children.get(name) if name != '.' else node
            if node is None or not node.is_folder:
                return None
        return node

    def selected(self, node):
        return node in self.shown

    def index_title(self):
        """Title of the folder page of the folder given paths share, if it is built: the one place
        a vault names itself, front matter title or leading heading; None without one."""
        top = self.common
        if top is not None and top.page and self.selected(top):
            return read_title(top.file)
        return None

    def shows(self, node):
        """Whether build shows node: selected one with its text, folder on the way to it by its title."""
        return node in self.shown or node in self.ancestors

    def inside(self, node):
        """Whether links to node lead to something built: selected page or folder, or title only folder."""
        return node in self.shown or node.is_folder and node.page is None and node in self.ancestors

    def show(self, node):
        """Path to show for page, folder or folder page file."""
        if not node.is_folder and node.folder and node.folder.page is node:
            node = node.folder
        if node in self.shown:
            return self.shown[node]
        return os.path.relpath(node.file or node.fullpath)
