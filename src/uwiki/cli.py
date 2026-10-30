"""Command line: uwiki build|check|stats|wrap."""

import argparse
import json
import os
import sys
from pathlib import Path

from .build import MDRenderer, Renderer
from .check import Checker
from .stats import Stats
from .vault import Scanner
from .wrap import WIDTH, wrap_files

def build(args, parser):
    path = os.path.abspath(args.folder)
    if not os.path.isdir(path):
        parser.error(f'not a directory: {args.folder}')
    title = args.title or Path(path).name
    both = not args.html and not args.md
    os.makedirs(args.output, exist_ok=True)
    output = os.path.join(args.output, title)

    scanner = Scanner(path, title)
    scanner.scan()
    if args.html or both:
        Renderer(scanner, args.output).write(f'{output}.html', title)
    if args.md or both:
        MDRenderer(scanner, args.output).write(f'{output}.md')

def report(problems):
    for problem in problems:
        print(problem)
    return 1 if problems else 0

def check(args, parser):
    return report(Checker(args.paths).check())

def stats(args, parser):
    res = Stats(args.paths, args.by).collect()
    print(json.dumps(res.data(args.top), indent=2, ensure_ascii=False) if args.json else res.report(args.top))

def wrap(args, parser):
    return report(wrap_files(args.files, args.width, args.check))

def main():
    parser = argparse.ArgumentParser(prog='uwiki', description='Markdown utility for Obsidian vaults and other wikis.')
    commands = parser.add_subparsers(dest='command', required=True, metavar='command')

    p = commands.add_parser('build', help='build folder of markdown files into single HTML and markdown file')
    p.add_argument('folder', help='folder with markdown files, e.g. Obsidian vault')
    p.add_argument('title', nargs='?', help='default: folder name')
    p.add_argument('--html', action='store_true', help='write HTML only (default: both HTML and markdown)')
    p.add_argument('--md', action='store_true', help='write single markdown file only')
    p.add_argument('-o', '--output', default='.', help='output directory, default: current')
    p.set_defaults(func=build)

    p = commands.add_parser('check', help='check unresolved wiki links and headings, missing images, '
                                          'frontmatter syntax and list numbering')
    p.add_argument('paths', nargs='+', metavar='path', help='folders or files to check')
    p.set_defaults(func=check)

    p = commands.add_parser('stats', help='count pages, words, headings, list items and links')
    p.add_argument('paths', nargs='+', metavar='path', help='folders or files to count')
    p.add_argument('--by', default='folder', metavar='KEY', help='group by folder (default) or frontmatter key')
    p.add_argument('--top', type=int, default=5, help='list N largest pages, default: 5')
    p.add_argument('--json', action='store_true', help='print JSON with every page')
    p.set_defaults(func=stats)

    p = commands.add_parser('wrap', help='rewrap long lines of paragraphs and list items in place')
    p.add_argument('files', nargs='+', metavar='file')
    p.add_argument('-w', '--width', type=int, default=WIDTH, help=f'default: {WIDTH}, tab counts as 4')
    p.add_argument('--check', action='store_true', help='report lines to rewrap instead, exit 1 if any')
    p.set_defaults(func=wrap)

    args = parser.parse_args()
    sys.exit(args.func(args, parser) or 0)
