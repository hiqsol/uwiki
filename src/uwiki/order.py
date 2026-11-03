"""Links between pages and reading order of pages in a folder, one for build, llms and the sidebar."""

from .convert import Converter

class LinkCollector(Converter):
    """Reads page like renderer does, notes its links and embeds in order: target and heading."""

    def __init__(self, page, scanner):
        super().__init__(page, scanner)
        self.mode = 'md'
        self.found = []  # (target, heading, line)

    def local_href(self, href, line=None):
        if self.is_local(href):
            target, heading = self.resolve_href(href)
            fragment = href.partition('#')[2]
            self.note(target, fragment if self.ITEM.fullmatch(fragment) else heading, line)
        return super().local_href(href, line)

    def link(self, text, checked=False):
        name, heading, item, _ = self.parse_target(text)
        target = self.scanner.resolve(name, self.source.path) if name else self.page
        heading = '' if heading.startswith('^') else heading
        if item and target is not None:
            heading = self.title_section(target, heading)
        self.note(target, ' › '.join(filter(None, [heading, item])))
        return super().link(text, checked)

    def embed_note(self, text):
        self.link(text)
        return ''

    def note(self, target, heading='', line=None):
        if target is not None:
            self.found.append((target, heading, self.line if line is None else line))

class Links:
    """Links of vault pages, read once: folder page links are its folder's."""

    def __init__(self, scanner):
        self.scanner = scanner
        self.cache = {}
        self._reach = None

    def of(self, node):
        """Links of page or folder page in order, as (target, heading, line), headings found or None if missing."""
        if node not in self.cache:
            collector = LinkCollector(node, self.scanner)
            try:
                collector.read()
            except ValueError:
                pass
            self.cache[node] = collector.found
        return self.cache[node]

    def targets(self, node):
        """Pages and folders node links to, in order of first link."""
        return list(dict.fromkeys(target for target, _, _ in self.of(node)))

    def reach(self):
        """Node: order it is first reached in, in a breadth-first walk of links from the root folder page."""
        if self._reach is None:
            root = self.scanner.root
            self._reach = {}
            if root.page:
                self._reach[root] = 0
                todo = [root]
                for node in todo:
                    for target in self.targets(node):
                        if target not in self._reach:
                            self._reach[target] = len(self._reach)
                            todo.append(target)
        return self._reach

class Order:
    """Reading order of pages and folders in a folder.

    Folder page first, then pages it links in order of its links, every other page right after
    the first page linking it, recursively, so related pages stay together, general before specific.
    Pages no page of the folder links go by first reach from the root folder page, unreachable ones by name.
    Link to a page inside a subfolder counts for the subfolder, a subfolder links what its folder page does.
    """

    def __init__(self, scanner, links=None):
        self.scanner = scanner
        self.links = links or Links(scanner)
        self.cache = {}

    def children(self, folder):
        if folder not in self.cache:
            self.cache[folder] = self.sort(folder)
        return self.cache[folder]

    def sort(self, folder):
        kids = list(folder.children.values())
        owner = {}
        for kid in kids:
            for node in self.inner(kid):
                owner[node] = kid
        seen = set()
        res = []

        def visit(node):
            claimed = [owner[t] for t in self.links.targets(node) if t in owner]
            claimed = [kid for kid in dict.fromkeys(claimed) if kid not in seen and kid is not node]
            seen.update(claimed)
            for kid in claimed:
                res.append(kid)
                visit(kid)

        if folder.page:
            visit(folder)
        if len(seen) == len(kids):
            return res
        # walking links from the root reads the whole vault, so only for pages the folder does not link
        reach = self.links.reach()
        first = {kid: min((reach[n] for n in self.inner(kid) if n in reach), default=None) for kid in kids}
        rest = sorted(range(len(kids)), key=lambda i: (first[kids[i]] is None, first[kids[i]] or 0, i))
        for kid in (kids[i] for i in rest):
            if kid not in seen:
                seen.add(kid)
                res.append(kid)
                visit(kid)
        return res

    @staticmethod
    def inner(node):
        """Node and, for a folder, every page and folder in it."""
        yield node
        if node.is_folder:
            for child in node.children.values():
                yield from Order.inner(child)
