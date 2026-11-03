"""Lists markdown files as uwiki takes them, or external links in them, for other tools to take."""

import re

from .convert import Converter
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

    @classmethod
    def trim(cls, url):
        """Drops trailing punctuation and closing parentheses url does not open, as GitHub autolinks do."""
        while url[-1] in cls.TRAILING or url[-1] == ')' and url.count(')') > url.count('('):
            url = url[:-1]
        return url
