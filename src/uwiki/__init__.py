"""uWiki: builds, checks, counts and wraps markdown wikis, e.g. Obsidian vaults."""

__version__ = "0.3.1"

from .check import Checker
from .stats import Stats
from .vault import Folder, Page, Scanner, Vaults
from .wrap import rewrap, wrap_files

def check(paths):
    """Problems of given folders or files as `path:line: message` lines."""
    return Checker(paths).check()

def stats(paths, by='folder', top=5):
    """Statistics of given folders or files as data, see `uwiki stats --json`."""
    return Stats(paths, by).collect().data(top)
