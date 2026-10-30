"""Vault model: pages, folders and Obsidian-like link resolution."""

import os
import re
from pathlib import Path

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
            # page `Name.md` and folder `Name/` can sit side by side
            self.children[name if is_folder else name + '.md'] = res
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


class Vaults:
    """Markdown files under given paths, each with the vault it links in, paths in one vault share it."""

    def __init__(self, paths):
        self.paths = paths
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
            scanner = Scanner(root, '')
            scanner.scan()
            pages = {}
            def collect(folder):
                if folder.page:
                    pages[folder.page.fullpath] = folder
                for child in folder.children.values():
                    if child.is_folder:
                        collect(child)
                    else:
                        pages[child.fullpath] = child
            collect(scanner.root)
            self.vaults[root] = scanner, pages
        return self.vaults[root]

    @staticmethod
    def loose_page(scanner, file):
        """Page for a file scanner skipped, e.g. hidden one."""
        return Page(None, Path(file).stem, os.path.splitext(file[len(scanner.path):])[0], file)
