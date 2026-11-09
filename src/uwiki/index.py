"""Fills marked blocks of pages with the pages of their folder, a line each from its front matter."""

import difflib
import itertools
import os
import re

from .config import Config, ConfigError
from .vault import Filter, Vaults, front_matter_items, read_parts

class Index:
    """Blocks `<!-- generated: NAME -->` ... `<!-- /generated -->` list the other pages of the folder they are in.

    `[index.NAME]` of config gives the block's `line`, `{key}` being front matter key, `{title}`, `{stem}` or
    `{path}` relative to the page; `sort` by a key, `-key` descending, else lines stay in their order and new pages
    go after the last one by path; `empty` line when no page is left; `exclude` globs from the config folder.
    Lines linking a subfolder are written by hand and stay.
    """

    OPENING = '<!-- generated: '
    CLOSING = '<!-- /generated -->'
    BLOCK = re.compile(f'({re.escape(OPENING)}([\\w-]+) -->\n)(.*?)({re.escape(CLOSING)})', re.DOTALL)
    LINK = re.compile(r'\[[^\]]*\]\(<?([^)\s>]+)>?\)')
    FIELD = re.compile(r'\{([\w.-]+)\}')
    LINE = '- [{title}]({path}): {description}'

    def __init__(self, paths, include=(), exclude=()):
        self.vaults = Vaults(paths, Filter(include, exclude))
        self.configs = {}
        self.problems = []

    def changes(self):
        """(path to show, current text, new text) of pages whose blocks are out of date."""
        res = []
        for scanner, node, shown in self.vaults.files():
            page = node.source
            text = read_parts(page.fullpath)[0]
            if self.OPENING not in text:
                continue
            folder = node if node.is_folder else node.folder
            new = self.BLOCK.sub(lambda m: self.block(m, scanner, folder, page, shown), text)
            if new != text:
                res.append((shown, text, new))
        return res

    def block(self, match, scanner, folder, page, shown):
        opening, name, body, closing = match.groups()
        config = self.config(scanner)
        table = config.data.get('index', {}).get(name, {})
        if not isinstance(table, dict):
            raise ConfigError(f'{config.path}: index.{name} should be a table')
        unknown = set(table) - {'line', 'sort', 'empty', 'exclude'}
        if unknown:
            raise ConfigError(f'{config.path}: unknown option {", ".join(sorted(unknown))} of index.{name}')
        ignored = [Filter.compile(glob) for glob in table.get('exclude', [])]
        pages = {}
        for child in sorted(folder.children.values(), key=lambda c: c.fullpath):
            if child.is_folder or child is page:
                continue
            path = os.path.relpath(child.fullpath, scanner.path).replace(os.sep, '/')
            if not any(glob.fullmatch(f'{config.prefix}/{path}' if config.prefix else path) for glob in ignored):
                pages[os.path.realpath(child.fullpath)] = child
        line = lambda child: self.line(table.get('line', self.LINE), child, page, shown)
        kept, listed, last = [], set(), 0
        for text in filter(str.strip, body.splitlines()):
            target = self.target(text, page)
            if target in pages and 'sort' not in table:
                kept.append(line(pages[target]))
                listed.add(target)
                last = len(kept)
            elif target and self.subfolder(target, folder):
                kept.append(text)
        if 'sort' in table:
            key = table['sort'].lstrip('-')
            values = lambda child: dict(front_matter_items(read_parts(child.fullpath)[1]))
            new = sorted(pages.values(), key=lambda child: os.path.basename(child.fullpath))
            new.sort(key=lambda child: str(values(child).get(key, '')), reverse=table['sort'].startswith('-'))
            lines = [*map(line, new), *kept]
        else:
            new = [child for target, child in pages.items() if target not in listed]
            lines = kept[:last] + list(map(line, new)) + kept[last:]
        if not lines and 'empty' in table:
            lines = [table['empty']]
        return opening + ''.join(f'{text}\n' for text in lines) + closing

    def line(self, template, child, page, shown):
        values = dict(front_matter_items(read_parts(child.fullpath)[1]))
        path = os.path.relpath(child.fullpath, os.path.dirname(page.fullpath)).replace(os.sep, '/')
        values.update(path=path, stem=os.path.splitext(os.path.basename(child.fullpath))[0], title=child.title)

        def field(match):
            value = values.get(match[1])
            if value in (None, '', []):
                self.problems.append(f'{shown}: {path}: no front matter {match[1]} for its index line')
                return ''
            return ' '.join((', '.join(value) if isinstance(value, list) else value).split())
        return self.FIELD.sub(field, template)

    def target(self, text, page):
        """Real path of the file the first link of the line leads to, None without one."""
        link = self.LINK.search(text)
        if not link or ':' in link[1]:
            return None
        return os.path.realpath(os.path.join(os.path.dirname(page.fullpath), link[1].partition('#')[0]))

    @staticmethod
    def subfolder(target, folder):
        return any(child.is_folder and target in (os.path.realpath(child.fullpath), child.file and
                   os.path.realpath(child.file)) for child in folder.children.values())

    def config(self, scanner):
        if scanner not in self.configs:
            self.configs[scanner] = Config.load(scanner.path)
        return self.configs[scanner]

    @staticmethod
    def diff(shown, current, new):
        """Problem line and the lines that differ, as `--check` reports them."""
        pairs = itertools.zip_longest(current.splitlines(), new.splitlines())
        line = next(n for n, (a, b) in enumerate(pairs, 1) if a != b)
        res = [f'{shown}:{line}: index out of date, rerun without --check']
        for text in difflib.unified_diff(current.splitlines(), new.splitlines(), lineterm='', n=0):
            if text[:1] in '-+' and not text.startswith(('---', '+++')):
                res.append(f'  {text}')
        return res
