"""Checks vault the way it builds: links, headings, images, frontmatter, list numbering, orphans."""

import os
import re
from dataclasses import dataclass, fields
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from .config import Config
from .convert import Converter
from .mention import Mentions
from .order import Links
from .vault import Filter, Scanner, Vaults, front_matter_items, front_matter_tree, read_aliases, read_parts

@dataclass
class CheckOptions:
    folder_links: bool = True
    orphans: bool = False
    unlisted: bool = False
    mentions: bool = False
    mentions_ignore: tuple = ()
    mentions_min_length: int = 3
    mentions_ignore_case: bool = False
    mentions_every: bool = False
    mentions_self_bold: bool = False
    mentions_exclude: tuple = ()
    max_lines: int = 0
    max_lines_ignore: tuple = ()
    acyclic: tuple = ()
    stale_days: int = 0
    stale_date: tuple = ()
    stale_until: str = ''

    @classmethod
    def from_values(cls, values):
        """Options of config values, as `check` takes them: `folder-links = false`, `no-folder-links = true`."""
        names = {field.name for field in fields(cls)}
        res = {}
        for key, value in values.items():
            name = key.replace('-', '_')
            if name in names:
                res[name] = tuple(value) if isinstance(value, list) else value
            elif name.startswith('no_') and name[3:] in names:
                res[name[3:]] = not value
        return cls(**res)

class CheckConverter(Converter):
    """Converts page like renderer does, reports what would render broken."""

    IMAGE = re.compile(r'!\[[^\]]*\]\(([^)\s]+)\)')
    NUMBERED = re.compile(r'^([ \t]*)(\d+)\. ')

    def __init__(self, page, scanner, report, options):
        super().__init__(page, scanner)
        self.report = report
        self.options = options
        self.mode = 'md'
        self.lists = []  # [indent, last number] of open numbered lists, outermost first
        self.blank = False

    def process_line(self, line):
        for n, raw in enumerate(line.splitlines(keepends=True)):
            self.check_numbering(raw, self.line + n)
        return super().process_line(line)

    def process_links(self, text):
        res = super().process_links(text)
        for src in self.IMAGE.findall(text):
            if '://' not in src and not (Path(self.source.fullpath).parent / src).exists():
                self.report(self.line, f'missing image: {src}')
        return res

    def markdown_link(self, match):
        if not match[1]:
            self.check_href(match[3], self.line + match.string.count('\n', 0, match.start()))
        return super().markdown_link(match)

    def link_definition(self, match):
        self.check_href(match[1].strip('<>'), self.line)
        return super().link_definition(match)

    def check_href(self, href, line):
        """Relative link names existing file inside vault, as spelled, page link also its heading."""
        path, _, fragment = unquote(href).partition('#')
        if ':' in path or path.startswith('//'):
            return
        if path.startswith('/'):
            return self.report(line, f'absolute link: {href}')
        if Scanner.vault_path(path, self.source.path) is None:
            return self.report(line, f'link leaves vault: {href}')
        target, heading = self.resolve_href(href)
        if target is not None and self.ITEM.fullmatch(fragment):
            node = target.source
            heading = True
            if node is None or not self.find_item(node, '', fragment):
                self.report(line, f'missing item: {href}')
        file = os.path.join(os.path.dirname(self.source.fullpath), path)
        if path and not os.path.exists(file):
            return self.report(line, f'link differs from file name: {href}' if target else f'unresolved link: {href}')
        if target is None and path.lower().endswith('.md'):
            return self.report(line, f'unresolved link: {href}')
        if path and os.path.isdir(file) and not self.options.folder_links:
            self.report(line, f'folder link: {href}')
        elif target is not None and heading is None:
            self.report(line, f'missing heading: {href}')

    def link(self, text, checked=False):
        self.check_link(text)
        return super().link(text, checked)

    def embed_note(self, text):
        self.check_link(text)
        return ''

    def check_link(self, text):
        name, heading, item, _ = self.parse_target(text)
        target = self.scanner.resolve(name, self.source.path) if name else self.source
        if target is None:
            if heading or item or not self.attachment(text):
                self.report(self.line, f'unresolved link: [[{name}]]')
            return
        node = target.source
        if heading and not heading.startswith('^'):
            if node is None or not self.section(self.read_text(node)[0], heading):
                return self.report(self.line, f'missing heading: [[{name}#{heading}]]')
        if item and (node is None or not self.find_item(node, self.title_section(target, heading), item)):
            self.report(self.line, f'missing item: [[{text.partition("|")[0].strip()}]]')

    def check_numbering(self, line, lineno):
        """Numbered lists count from 1, nesting by indentation, lazy continuation lines keep list going."""
        m = self.NUMBERED.match(line)
        if not m:
            if line.strip() and not line[0].isspace() and (self.blank or self.LIST_BREAK.match(line)):
                self.lists = []
            self.blank = not line.strip()
            return
        self.blank = False
        indent, num = len(m[1].expandtabs(4)), int(m[2])
        while self.lists and self.lists[-1][0] > indent:
            self.lists.pop()
        if not self.lists or self.lists[-1][0] < indent:
            self.lists.append([indent, 0])
        expected = self.lists[-1][1] + 1
        if num != expected:
            self.report(lineno, f'list number {num}, expected {expected}')
        self.lists[-1][1] = num

class Checker:
    """Checks vault consistency the way builder sees it, reports problems as `path:line: message`."""

    FRONT_MATTER_START = re.compile(r'\A---[ \t]*\r?\n')
    DAY = re.compile(r'\d{4}-\d\d-\d\d')
    FENCE = re.compile(r' {0,3}(`{3,}|~{3,})')
    CODE_SPAN = re.compile(r'(`+)([^`\n]+?)\1(?!`)')
    CODE_PATH = re.compile(r'[\w.-]+(?:/[\w.-]+)*/?')

    def __init__(self, paths, include=(), exclude=(), options=None, today=None):
        self.vaults = Vaults(paths, Filter(include, exclude))
        self.options = options or CheckOptions()
        self.problems = []
        self.warnings = []
        self.issues = {}  # real path of page file: [(line, message, warning)]
        self.links = {}  # scanner: links of its pages
        self.checked = {}  # checked page: (scanner, path to show)
        self.configs = {}  # scanner: its vault config
        self.today = today or datetime.now(timezone.utc).date()
        self.edges = {}  # (page, key): pages its page valued key names

    def check(self):
        for scanner, page, shown in self.vaults.files():
            self.checked[page] = scanner, shown
            self.check_file(scanner, page, shown)
        if self.options.orphans:
            self.check_orphans()
        if self.options.unlisted:
            self.check_unlisted()
        if self.options.mentions:
            self.check_mentions()
        self.check_layers()
        self.check_acyclic()
        return self.problems

    def check_acyclic(self):
        """Chains of page valued front matter keys, `[check] acyclic = ["supersedes"]`, lead back to no page,
        each key a chain of its own."""
        for key in self.options.acyclic:
            for page, (scanner, shown) in self.checked.items():
                cycle = self.cycle(scanner, page, key)
                if cycle:
                    show = lambda node: os.path.relpath(node.file, scanner.path).replace(os.sep, '/')
                    front = read_parts(page.source.fullpath)[1]
                    self.add(page, shown, self.key_line(front, key),
                             f'{key} chain leads back to it: {" -> ".join(show(node) for node in cycle)}')

    def cycle(self, scanner, page, key):
        """Pages from page back to it by values of key, breadth first so the shortest, None if none lead back."""
        parents = {}
        queue = [page]
        while queue:
            node = queue.pop(0)
            for target in self.named_by(scanner, node, key):
                if target is page:
                    chain = [node]
                    while chain[-1] is not page:
                        chain.append(parents[chain[-1]])
                    return [*reversed(chain), page]
                if target not in parents:
                    parents[target] = node
                    queue.append(target)
        return None

    def named_by(self, scanner, page, key):
        """Pages front matter key of page names, as `page` typed values name them."""
        if (page, key) not in self.edges:
            res = []
            if page.source is not None:
                try:
                    front = read_parts(page.source.fullpath)[1]
                except (OSError, UnicodeDecodeError):
                    front = ''
                value = front_matter_tree(front).get(key) if front else None
                for name in value if isinstance(value, list) else [value]:
                    target = self.page_named(scanner, page.source, name) if isinstance(name, str) else None
                    if target is not None:
                        res.append(target)
            self.edges[page, key] = res
        return self.edges[page, key]

    def check_stale(self, scanner, source, front, report):
        """Warns about a page whose latest date of stale_date keys is more than stale_days days ago, or whose
        stale_until date has come: nobody wrote or verified it since, or the snapshot it holds stopped holding."""
        o = self.options
        if not front or not (o.stale_days and o.stale_date or o.stale_until):
            return
        tree = front_matter_tree(front)
        if o.stale_days:
            dates = [(self.day(value), key) for key in o.stale_date for value in self.values_at(tree, key)]
            dates = [(day, key) for day, key in dates if day is not None]
            if dates:
                day, key = max(dates)
                ago = (self.today - day).days
                if ago > o.stale_days:
                    report(self.key_line(front, key.split('.')[0]),
                           f'stale: {key} {day.isoformat()}, {ago} days ago, more than {o.stale_days}')
        if o.stale_until:
            until = [day for day in map(self.day, self.values_at(tree, o.stale_until)) if day is not None]
            if until and min(until) <= self.today:
                report(self.key_line(front, o.stale_until.split('.')[0]),
                       f'stale: {o.stale_until} {min(until).isoformat()} passed')

    @classmethod
    def values_at(cls, tree, key):
        """Text values of dotted key in front matter tree, in a map or in every map of a list."""
        head, _, rest = key.partition('.')
        value = tree.get(head) if isinstance(tree, dict) else None
        for item in value if isinstance(value, list) else [value]:
            if rest:
                yield from cls.values_at(item, rest)
            elif isinstance(item, str):
                yield item

    @classmethod
    def day(cls, value):
        """Date a front matter date or datetime value starts with, None if it does not."""
        m = cls.DAY.match(value.strip())
        try:
            return date.fromisoformat(m[0]) if m else None
        except ValueError:
            return None

    def check_code_paths(self, scanner, source, text, front, report):
        """Code spans naming a path, ending in `.md` or holding a `/`, in pages a `[check.code-paths]` glob
        matches, name a file or folder in the folder it gives: pages shown as text, not linked, still point
        where they say."""
        config = self.config(scanner)
        bases = [base for glob, base in config.code_paths.items() if self.matches(scanner, source, [glob])]
        if not bases:
            return
        folder = os.path.dirname(config.path)
        fence = None
        for n, line in enumerate(text.splitlines()[front.count('\n'):], front.count('\n') + 1):
            m = self.FENCE.match(line)
            if m and (fence is None or m[1][0] == fence[0] and len(m[1]) >= len(fence)):
                fence = m[1] if fence is None else None
                continue
            if fence is not None:
                continue
            for span in self.CODE_SPAN.finditer(line):
                path = span[2].strip()
                if not self.CODE_PATH.fullmatch(path) or not (path.endswith('.md') or '/' in path):
                    continue
                if not any(os.path.exists(os.path.join(folder, base, path)) for base in bases):
                    report(n, f'missing path: {path} in {", ".join(bases)}')

    def add(self, page, shown, line, message, warning=False):
        """Reports problem or warning of page as `path:line: message`, keeps it by page file too."""
        if warning:
            self.warnings.append(f'{shown}:{line}: warning: {message}')
        else:
            self.problems.append(f'{shown}:{line}: {message}')
        file = page.file or page.source.fullpath
        self.issues.setdefault(os.path.realpath(file), []).append((line, message, warning))

    def check_mentions(self):
        """Warns about plain text mentions of another page title or alias: the first one of a page the page does not
        link, or every one with mentions_every; pages a mentions_exclude glob matches have none."""
        mentions = {}
        for page, (scanner, shown) in self.checked.items():
            if self.matches(scanner, page.source, self.options.mentions_exclude):
                continue
            if scanner not in mentions:
                o = self.options
                mentions[scanner] = Mentions(scanner, o.mentions_ignore, o.mentions_min_length, o.mentions_ignore_case)
            linked = set() if self.options.mentions_every else self.targets(scanner, page)
            seen = set()
            for mention in mentions[scanner].find(page, own=self.options.mentions_self_bold):
                if mention.own:
                    self.add(page, shown, mention.line + 1, f'own term not bold: {mention.text}', True)
                    continue
                if mention.node in linked or mention.node in seen:
                    continue
                if not self.options.mentions_every:
                    seen.add(mention.node)
                self.add(page, shown, mention.line + 1, f'unlinked mention: {mention.text}', True)

    def check_unlisted(self):
        """Warns about pages and folders their folder page does not link, as contents should."""
        for page, (scanner, shown) in self.checked.items():
            folder = page.folder
            if folder is None or folder.page is None or page is scanner.root:
                continue
            if page not in self.targets(scanner, folder):
                self.add(page, shown, 1, f'not listed in {folder.page.name}.md', True)

    def vault_links(self, scanner):
        if scanner not in self.links:
            self.links[scanner] = Links(scanner)
        return self.links[scanner]

    def targets(self, scanner, page):
        """Pages and folders page links to, as build and its reading order see them."""
        return self.vault_links(scanner).targets(page)

    def check_orphans(self):
        """Pages no chain of links leads to from the root folder page, naming the reason."""
        vaults = {}
        for page, (scanner, shown) in self.checked.items():
            if scanner not in vaults:
                vaults[scanner] = self.vault_links(scanner).orphans()
            reason = vaults[scanner].get(page)
            if reason:
                self.add(page, shown, 1, f'orphan page: {reason}')

    def check_layers(self):
        """Pages of a layer link only to pages of their layer or earlier ones, a folder page but the root one comes
        no later than its pages, by config `[check] layers.KEY = [values in order]`; pages of other values are
        outside layers, links to and from them go unchecked, a folder page outside is later than any layer."""
        for page, (scanner, shown) in self.checked.items():
            layers = self.config(scanner).layers
            if not layers:
                continue
            for key, values in layers.items():
                level = self.layer(page, key, values)
                if level is not None:
                    for target, _, line in self.vault_links(scanner).of(page):
                        other = self.layer(target, key, values) if target is not page else None
                        if other is not None and other > level:
                            path = os.path.relpath(target.file, scanner.path).replace(os.sep, '/')
                            self.add(page, shown, line, f'{values[level]} page links {values[other]} page: {path}')
                if page.is_folder and page is not scanner.root:
                    self.check_folder_layer(page, shown, scanner, key, values)

    def check_folder_layer(self, folder, shown, scanner, key, values):
        """Folder page of a later layer than its pages, or outside layers: filtering by layer would miss it."""
        level = self.layer(folder, key, values)
        children = [child for child in folder.children.values() if child.file]
        earlier = [(self.layer(child, key, values), child) for child in children]
        earlier = sorted((n, child.file) for n, child in earlier if n is not None and (level is None or n < level))
        if not earlier:
            return
        first = os.path.relpath(earlier[0][1], scanner.path).replace(os.sep, '/')
        more = f' and {len(earlier) - 1} more' if len(earlier) > 1 else ''
        _, front, _, _ = read_parts(folder.file)
        value = dict(front_matter_items(front)).get(key) if front else None
        name = values[level] if level is not None else value if isinstance(value, str) and value else f'no {key}'
        self.add(folder, shown, self.key_line(front, key),
                 f'{name} folder page of {values[earlier[0][0]]} page: {first}{more}')

    @staticmethod
    def layer(node, key, values):
        """Index of the earliest layer of node by its front matter key, None outside layers."""
        if node.file is None:
            return None
        try:
            items = dict(front_matter_items(read_parts(node.file)[1]))
        except ValueError:
            return None
        value = items.get(key)
        found = [values.index(v) for v in (value if isinstance(value, list) else [value]) if v in values]
        return min(found) if found else None

    def config(self, scanner):
        if scanner not in self.configs:
            self.configs[scanner] = Config.load(scanner.path)
        return self.configs[scanner]

    def schema(self, scanner):
        return self.config(scanner).schema

    def check_schema(self, scanner, source, front, report):
        """Front matter keys and values the vault config schema allows, required ones present."""
        schema = self.schema(scanner)
        if schema.empty:
            return
        path = os.path.relpath(source.fullpath, scanner.path).replace(os.sep, '/')
        resolve = lambda value: self.names_page(scanner, source, value)
        for key, message in schema.problems(front_matter_tree(front) if front else {}, path, resolve):
            report(self.key_line(front, key), message)

    @classmethod
    def names_page(cls, scanner, source, value):
        """Value names a page other than source: by name or `[[Page]]` as links do, or by path relative to it."""
        return cls.page_named(scanner, source, value) is not None

    @staticmethod
    def page_named(scanner, source, value):
        """Page other than source value names, see names_page, None if none."""
        name = value[2:-2].partition('|')[0] if value.startswith('[[') and value.endswith(']]') else value
        name = name.partition('#')[0].strip()
        if name.endswith('.md') or name.startswith('.'):
            target = scanner.resolve_path(name, source.path)
        else:
            target = scanner.resolve(name, source.path) if name else None
        return target if target is not None and target.source is not None and target.source is not source else None

    def check_length(self, scanner, source, text, report):
        """Page no longer than max_lines, unless a max_lines_ignore glob matches it from the config folder."""
        limit = self.options.max_lines
        lines = text.count('\n') + (not text.endswith('\n') and bool(text))
        if not limit or lines <= limit:
            return
        if not self.matches(scanner, source, self.options.max_lines_ignore):
            report(limit + 1, f'{lines} lines, more than {limit}')

    def matches(self, scanner, source, globs):
        """Whether a glob matches the source page's path from the config folder."""
        if not globs or source is None:
            return False
        path = os.path.relpath(source.fullpath, scanner.path).replace(os.sep, '/')
        return self.config(scanner).matches(path, globs)

    @staticmethod
    def key_line(front, key):
        """Line of front matter key, 1 if missing."""
        return next((n for n, text in enumerate(front.splitlines(), 1)
                     if key is not None and re.match(rf'[\'"]?{re.escape(key)}[\'"]?:', text)), 1)

    def check_aliases(self, scanner, page, front, report):
        """Aliases page names win over, aliases two pages share."""
        items = dict(front_matter_items(front)) if front else {}
        key = 'aliases' if 'aliases' in items else 'alias'
        for alias in read_aliases(page.file):
            show = lambda node: os.path.relpath(node.file or node.fullpath, scanner.path).replace(os.sep, '/')
            named = [node for folderless, node in scanner.named(alias) if not folderless and node is not page]
            if named:
                report(self.key_line(front, key), f'alias {alias}: {show(named[0])} has this name, links lead there')
            for _, other in scanner.aliases.get(alias.lower(), []):
                if other is not page:
                    report(self.key_line(front, key), f'alias {alias}: also alias of {show(other)}')

    def check_file(self, scanner, page, shown):
        report = lambda line, msg: self.add(page, shown, line, msg)
        source = page.source
        try:
            text, front, _, _ = read_parts(source.fullpath)
        except UnicodeDecodeError:
            return report(1, 'not UTF-8')
        for n, line in enumerate(front.splitlines()[1:-1], 2):
            if line and not line.startswith((' ', '-')) and ':' not in line:
                report(n, f'malformed frontmatter: {line}')
        if not front and self.FRONT_MATTER_START.match(text):
            report(1, 'unclosed frontmatter')
        self.check_schema(scanner, source, front, report)
        self.check_aliases(scanner, page, front, report)
        self.check_length(scanner, source, text, report)
        self.check_stale(scanner, source, front, lambda line, msg: self.add(page, shown, line, msg, True))
        self.check_code_paths(scanner, source, text, front, report)
        if page.folder and page.folder.shadowed_index() is page:
            report(1, Scanner.shadowed_message(page.folder))
        converter = CheckConverter(page, scanner, report, self.options)
        converter.read()

