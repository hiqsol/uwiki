"""Lists markdown files as uwiki takes them, external links in them or refs they define, for other tools."""

import re

from .convert import Converter
from .refs import Refs
from .vault import Filter, Vaults, read_text

class Listing:
    """Markdown files under given paths, after skip list and filters, and http links outside their code."""

    URL = re.compile(r'https?://\w[^\s<>\[\]"\'`]*')
    TRAILING = '.,:;!?*_~'

    def __init__(self, paths, include=(), exclude=()):
        self.vaults = Vaults(paths, Filter(include, exclude))

    def files(self):
        return [shown for _, _, shown in self.vaults.files()]

    def urls(self):
        """Unique http and https links outside front matter and code, sorted."""
        res = set()
        for _, page, _ in self.vaults.files():
            source = page.source
            try:
                text = read_text(source.fullpath)[0]
            except ValueError:
                continue
            for _, line in Converter.prose(text):
                res.update(map(self.trim, self.URL.findall(Converter.CODE.sub(' ', line))))
        return sorted(res)

    def refs(self):
        """Refs defined in the files, as `ref<TAB>path:line<TAB>what it defines`, by path and line:
        what agents grep to find where `doc:245` leads."""
        res = []
        for scanner, page, shown in self.vaults.files():
            refs = Refs.of(scanner)
            if refs and page.source is not None:
                res += [f'{d.ref}\t{shown}:{d.line}\t{d.text}' for d in refs.defined(page, page.source.fullpath)]
        return res

    @classmethod
    def trim(cls, url):
        """Drops trailing punctuation and closing parentheses url does not open, as GitHub autolinks do."""
        while url[-1] in cls.TRAILING or url[-1] == ')' and url.count(')') > url.count('('):
            url = url[:-1]
        return url
