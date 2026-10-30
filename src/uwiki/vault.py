"""Vault model: pages, folders and Obsidian-like link resolution."""

import os
import posixpath
import re
from pathlib import Path

FRONT_MATTER = re.compile(r'\A---[ \t]*\r?\n.*?^(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)', re.DOTALL | re.MULTILINE)
TITLE = re.compile(r'\A(\s*)(#{1,6})[ \t]+(.*?)[ \t]*(?:\r?\n|\Z)')

def read_text(path):
    """Returns file text without front matter and number of its first line."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
    except UnicodeDecodeError as e:
        raise ValueError(f'Error reading {path}') from e
    m = FRONT_MATTER.match(text)
    if not m:
        return text, 1
    return text[m.end():], m[0].count('\n') + 1

def read_title(path):
    """Front matter title, else heading the file starts with, if any."""
    text = read_file(path)
    m = FRONT_MATTER.match(text)
    title = front_matter_value(m[0] if m else '', 'title')
    if title:
        return title
    heading = TITLE.match(text[m.end():] if m else text)
    return heading[3] if heading else None

def read_description(path):
    m = FRONT_MATTER.match(read_file(path))
    return front_matter_value(m[0], 'description') if m else None

def read_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
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
        self.default_title = titleize(name)
        self._title = None
        self.anchor = cebabize(name)

    @property
    def file(self):
        return self.fullpath

    @property
    def title(self):
        """Front matter title or leading heading of the page, else its name."""
        if self._title is None:
            self._title = read_title(self.file) or self.default_title
        return self._title

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

    @property
    def file(self):
        return self.page.fullpath if self.page else None

    def build_child(self, is_folder, name, path, fullpath):
        if is_folder:
            return Folder(self, name, path, fullpath)
        else:
            return Page(self, name, path, fullpath)

    def child(self, is_folder, name, path, fullpath):
        res = self.build_child(is_folder, name, path, fullpath)
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

    def __str__(self):
        return f'Folder(name={self.name}, title={self.title}, path={self.path})'

    def __repr__(self):
        return self.__str__()

class Filter:
    """Takes vault paths: skip list and excludes drop them, includes take them back.

    Glob with `/` matches path from vault root, without it any path segment, like gitignore;
    matching folder matches everything in it.
    """
    SKIP = ('.*', 'node_modules', 'vendor')

    def __init__(self, include=(), exclude=()):
        self.include = [self.compile(p) for p in include]
        self.include_prefixes = [self.prefix(p) for p in include]
        self.drop = [self.compile(p) for p in (*self.SKIP, *exclude)]

    @staticmethod
    def compile(glob):
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
        return re.compile(res + '(?:/.*)?')

    @staticmethod
    def prefix(glob):
        """Literal start of anchored glob, empty for one matching anywhere."""
        glob = glob.strip('/')
        return re.split(r'[*?]', glob)[0] if '/' in glob else ''

    def takes(self, path):
        if any(p.fullmatch(path) for p in self.include):
            return True
        return not any(p.fullmatch(path) for p in self.drop)

    def enters(self, path):
        """Folder is scanned when taken or an include can take something in it."""
        path += '/'
        return self.takes(path[:-1]) or any(p.startswith(path) or path.startswith(p) for p in self.include_prefixes)

class Scanner:
    def __init__(self, path, title, filter=None):
        self.path = path
        self.root = Folder(None, Path(path).name, '', self.path)
        self.root.default_title = title
        self.root.anchor = 'root'
        self.filter = filter or Filter()
        self.targets = {}
        self.attachments = {}
        self.symlinks = []
        self.warnings = []

    def scan(self):
        self._scan_dir(self.root)
        self._index(self.root)
        self._alias_symlinks()
        self._assign_anchors()

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

    def resolve_path(self, path, source=''):
        """Finds link target by path relative to the source page, as markdown links give it."""
        path = posixpath.normpath(posixpath.join(posixpath.dirname(source).lstrip('/'), path)).lower()
        if path.startswith('..'):
            return None
        if path.endswith('.md'):
            path = path[:-3]
        path = '/' + path
        return next((node for p, node in self.targets.get(Path(path).name, []) if p == path), None)


class Vaults:
    """Markdown files under given paths, each with the vault it links in, paths in one vault share it."""

    def __init__(self, paths, filter=None):
        self.paths = paths
        self.filter = filter
        self.vaults = {}

    def files(self):
        """Yields scanner, page and path to show of every file once, folder pages give folders."""
        seen = set()
        folders = [p if os.path.isdir(p) else os.path.dirname(p) for p in map(os.path.abspath, self.paths)]
        common = os.path.commonpath(folders)
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
            scanner = Scanner(root, '', self.filter)
            scanner.scan()
            pages = scanner.pages()
            self.vaults[root] = scanner, pages
        return self.vaults[root]

    @staticmethod
    def loose_page(scanner, file):
        """Page for a file scanner skipped, e.g. hidden one."""
        return Page(None, Path(file).stem, os.path.splitext(file[len(scanner.path):])[0], file)
