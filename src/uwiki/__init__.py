"""uWiki: builds, checks, counts and wraps markdown wikis, e.g. Obsidian vaults."""

__version__ = "0.19.0"

from .check import Checker, CheckOptions
from .stats import Stats
from .vault import Filter, Folder, Page, Scanner, Vaults
from .wrap import rewrap, wrap_files

def check(paths, include=(), exclude=(), options=None):
    """Problems of given folders or files as `path:line: message` lines, see CheckOptions."""
    return Checker(paths, include, exclude, options).check()

def stats(paths, by='folder', top=5, include=(), exclude=()):
    """Statistics of given folders or files as data, see `uwiki stats --json`."""
    return Stats(paths, by, include, exclude).collect().data(top)
