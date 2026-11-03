"""Moves or renames a page, folder or attachment inside the vault, rewriting every link to it."""

import os
import posixpath
import subprocess
from urllib.parse import quote, unquote

from .config import Config
from .convert import Converter
from .vault import Filter, Scanner, Vaults, read_parts

class MoveError(ValueError):
    """Move that cannot be made."""

class Move:
    """Move of one page, folder or attachment in the vault it is in.

    Links resolve before the move in the vault as it is and after it in the vault as it will be,
    a wiki link changes only when it would lead elsewhere, to the shortest name leading right,
    a name only link stays name only when that is enough; relative markdown links and reference
    definitions point at the new place, links in moved pages are fixed for their new folder.
    """

    def __init__(self, source, target, include=(), exclude=()):
        source, target = os.path.abspath(source), os.path.abspath(target)
        if not os.path.exists(source):
            raise MoveError(f'no such file or folder: {source}')
        if os.path.isdir(target):
            target = os.path.join(target, os.path.basename(source))
        if os.path.exists(target):
            raise MoveError(f'already exists: {target}')
        if source.endswith('.md') != target.endswith('.md') and not os.path.isdir(source):
            raise MoveError('a page keeps its .md extension, an attachment gets none')
        self.root = self.vault_root(source, target)
        for path in (source, target):
            if not path.startswith(os.path.join(self.root, '')):
                raise MoveError(f'not inside the vault {self.root}: {path}')
        if target.startswith(os.path.join(source, '')):
            raise MoveError('cannot move a folder into itself')
        self.source, self.target = source, target
        self.src = self.rel(source)
        self.dst = self.rel(target)
        # files the config of the vault or the options leave out keep their text, e.g. a built wiki
        options = Config.load(self.root).options('mv', ())
        listed = lambda key: [options[key]] if isinstance(options.get(key), str) else list(options.get(key, []))
        self.old = Scanner(self.root, Filter([*listed('include'), *include], [*listed('exclude'), *exclude]))
        self.old.scan()
        files = self.old.files()
        self.new = Scanner.from_files(self.root, [self.moved(f) for f in files])
        self.new_pages = self.new.pages()
        # moved pages keep their aliases, read before the move
        self.new._aliases = {alias: [(node.path.lower(), node) for node in map(self.new_node, (n for _, n in entries))
                                     if node is not None]
                             for alias, entries in self.old.aliases.items()}
        self.changes = {}  # new relative path: (old text, new text)

    @staticmethod
    def vault_root(source, target):
        """Nearest folder with `.obsidian`, else current folder when both paths are in it, else their common one."""
        common = os.path.commonpath([os.path.dirname(source), os.path.dirname(target)])
        root = Vaults.vault_root(common, common)
        if root == common:
            cwd = os.getcwd()
            if all(p.startswith(os.path.join(cwd, '')) for p in (source, target)):
                return cwd
        return root

    def rel(self, path):
        return os.path.relpath(path, self.root).replace(os.sep, '/')

    def full(self, rel):
        return os.path.join(self.root, rel)

    def moved(self, rel):
        """Where vault relative path of a file or folder goes."""
        if rel == self.src or rel.startswith(self.src + '/'):
            return self.dst + rel[len(self.src):]
        return rel

    def plan(self):
        """Rewritten text of every page whose links change, by its new path."""
        for file, node in self.old.pages().items():
            try:
                text, front, body, _ = read_parts(file)
            except (OSError, UnicodeDecodeError):
                continue
            rel = self.rel(file)
            new = front + Rewriter(self, node, rel, self.moved(rel)).process(body)
            if new != text:
                self.changes[self.moved(rel)] = text, new
        return self.changes

    # what links lead to after the move

    def new_node(self, node):
        """Page or folder of the new vault the old one becomes."""
        if node.file:
            return self.new_pages.get(self.full(self.moved(self.rel(node.file))))
        return self.new.resolve_path(self.moved(node.path.strip('/')))

    @staticmethod
    def source_path(rel):
        """Page path as resolution takes it: `/folder/Page`."""
        return '/' + rel[:-3]

    def resolves(self, name, embed, kind, expected, source):
        """Whether wiki link name leads to expected page or attachment file in the new vault."""
        attachment = self.new.attachment(name, source)
        if kind == 'file':
            return attachment == expected and (embed or self.new.resolve(name, source) is None)
        return (not embed or attachment is None) and self.new.resolve(name, source) is expected

    def names(self, path, least):
        """Names of a path from just the last part to all of it, at least given parts."""
        parts = path.strip('/').split('/')
        return ['/'.join(parts[-k:]) for k in range(min(least, len(parts)), len(parts) + 1)]

    def wiki(self, text, embed, old_source, new_source):
        """New text inside `[[...]]`, None if the link still leads where it did."""
        target_part, bar, description = text.partition('|')
        if target_part.endswith('\\'):  # escaped in a table cell
            target_part, bar = target_part[:-1], '\\|'
        name, hash, heading = target_part.partition('#')
        name = name.strip()
        if not name:
            return None
        attachment = self.old.attachment(name, old_source)
        page = self.old.resolve(name, old_source)
        if attachment and (embed or page is None and not heading):
            kind, expected = 'file', self.full(self.moved(self.rel(attachment)))
            path = self.moved(self.rel(attachment))
        elif page is not None:
            kind, expected = 'page', self.new_node(page)
            if expected is None:
                return None
            path = self.rel(expected.file)[:-3] if expected.file and not expected.is_folder else expected.path
        else:
            return None
        if self.resolves(name, embed, kind, expected, new_source):
            return None
        md = '.md' if name.endswith('.md') and kind == 'page' else ''
        least = 1 if '/' not in name.strip('/') else len(name.strip('/').split('/'))
        names = self.names(path, least)
        new = next((n for n in names if self.resolves(n + md, embed, kind, expected, new_source)), names[-1])
        return new + md + hash + heading + bar + description

    def markdown(self, href, old_rel, new_rel):
        """New relative href of markdown link, None if it still leads where it did."""
        if not Converter.is_local(href):
            return None
        path, hash, fragment = href.partition('#')
        if not path:
            return None
        raw = unquote(path)
        target = Scanner.vault_path(raw, old_rel)
        if target is None:
            return None
        if not os.path.exists(self.full(target)):
            # spelled in other case, as check reports: follows the page it resolves to
            node = self.old.resolve_path(raw, self.source_path(old_rel))
            if node is None:
                return None
            target = self.rel(node.file) if node.file and not raw.endswith('/') else node.path.strip('/')
        moved = self.moved(target)
        if Scanner.vault_path(raw, new_rel) == moved:
            return None
        res = posixpath.relpath(moved, posixpath.dirname(new_rel) or '.')
        if raw.endswith('/'):
            res += '/'
        if raw.startswith('./') and not res.startswith('../'):
            res = './' + res
        if '%' in path or ' ' in res:
            res = quote(res)
        return res + hash + fragment

    def mention(self, text, old_rel, new_rel):
        """New spelling of a path named as inline code or link text, None unless it is a path with `/`
        to a file or folder, relative to the page or the vault root, that now has another spelling."""
        if '/' not in text or not Converter.is_local(text) or '#' in text:
            return None
        for old_base, new_base in ((old_rel, new_rel), ('', '')):
            target = Scanner.vault_path(text, old_base)
            if target is None or target == '.' or not os.path.exists(self.full(target)):
                continue
            res = posixpath.relpath(self.moved(target), posixpath.dirname(new_base) or '.')
            if text.endswith('/'):
                res += '/'
            if text.startswith('./') and not res.startswith('../'):
                res = './' + res
            return None if res == text else res
        return None

    # doing it

    def diff(self, shown):
        """The move and every changed line, - before and + after, as `path:line: text`."""
        lines = [f'mv {shown(self.source)} {shown(self.target)}']
        for rel, (old, new) in sorted(self.changes.items()):
            path = shown(self.full(rel))
            for n, (a, b) in enumerate(zip(old.splitlines(), new.splitlines()), 1):
                if a != b:
                    lines += [f'{path}:{n}: - {a}', f'{path}:{n}: + {b}']
        return lines

    def run(self):
        """Moves with git mv in a git work tree, plain rename otherwise, then writes rewritten pages."""
        os.makedirs(os.path.dirname(self.target), exist_ok=True)
        if self.in_git():
            subprocess.run(['git', 'mv', '-k', self.source, self.target], cwd=self.root,
                           capture_output=True, check=False)
        if os.path.isdir(self.source):
            for folder, _, files in os.walk(self.source, topdown=False):
                for name in files:
                    rel = self.rel(os.path.join(folder, name))
                    os.renames(self.full(rel), self.full(self.moved(rel)))
        elif os.path.exists(self.source):
            os.renames(self.source, self.target)
        for rel, (_, new) in self.changes.items():
            with open(self.full(rel), 'w', encoding='utf-8') as f:
                f.write(new)

    def in_git(self):
        try:
            res = subprocess.run(['git', 'rev-parse', '--is-inside-work-tree'], cwd=self.root,
                                 capture_output=True, text=True, check=False)
        except OSError:
            return False
        return res.stdout.strip() == 'true'

class Rewriter(Converter):
    """Rewrites links of a page where converter reads them: outside front matter, fenced and inline code,
    and paths named as whole inline code or link text, e.g. `docs/` or [docs/Guide.md](docs/Guide.md)."""

    def __init__(self, move, page, old_rel, new_rel):
        super().__init__(page, move.old)
        self.mode = 'md'
        self.move, self.old_rel, self.new_rel = move, old_rel, new_rel
        self.old_source, self.new_source = move.source_path(old_rel), move.source_path(new_rel)

    def process_line(self, line):
        if self.LINK_DEF.match(line):
            return self.LINK_DEF.sub(self.link_definition, line, count=1)
        return self.links(line)

    def wikilink(self, match):
        new = self.move.wiki(match[2], bool(match[1]), self.old_source, self.new_source)
        return match[0] if new is None else f'{match[1]}[[{new}]]'

    def markdown_link(self, match):
        if match[1]:
            return self.code_mention(match[0], match[1])
        text = self.text_mention(match[2])
        new = self.move.markdown(match[3], self.old_rel, self.new_rel)
        if new is None and text is None:
            return match[0]
        start = match.start(3) - match.start()
        between = match[0][1 + len(match[2]):start]
        return f'[{text or match[2]}{between}{new or match[3]}{match[0][start + len(match[3]):]}'

    def code_mention(self, code, ticks):
        new = self.move.mention(code[len(ticks):-len(ticks)], self.old_rel, self.new_rel)
        return code if new is None else ticks + new + ticks

    def text_mention(self, text):
        """New link text when it is a path, maybe as inline code, None if it stays."""
        ticks = len(text) - len(text.lstrip('`'))
        if ticks and text.endswith('`' * ticks) and len(text) > 2 * ticks:
            new = self.code_mention(text, '`' * ticks)
            return None if new == text else new
        return self.move.mention(text, self.old_rel, self.new_rel)

    def link_definition(self, match):
        href = match[1]
        new = self.move.markdown(href.strip('<>'), self.old_rel, self.new_rel)
        if new is None:
            return match[0]
        new = f'<{new}>' if href.startswith('<') else new
        return match[0][:match.start(1) - match.start()] + new
