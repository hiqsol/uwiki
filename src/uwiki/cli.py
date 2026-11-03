"""Command line: uwiki <command> <folder|file>... [options]."""

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .build import Build, BuildOptions, UsageError
from .check import Checker, CheckOptions
from .llms import Llms
from .ls import Listing
from .stats import Stats
from .vault import Filter, Selection
from .wrap import WIDTH, wrap_files

FILTER_USAGE = '[--exclude GLOB] [--include GLOB]'

def report(problems):
    for problem in problems:
        print(problem)
    return 1 if problems else 0

def build(args, parser):
    builder = Build(args.paths, args.output, args.title, args.html, args.md, args.include, args.exclude,
                    build_options(args))
    problems = builder.run()
    for warning in builder.warnings:
        print(f'warning: {warning}', file=sys.stderr)
    return report(problems)

def build_options(args):
    return BuildOptions(backlinks=not args.no_backlinks, front_matter=not args.no_front_matter)

def check(args, parser):
    options = CheckOptions(folder_links=not args.no_folder_links, orphans=args.orphans, unlinked=args.unlinked,
                           unlisted=args.unlisted)
    checker = Checker(args.paths, args.include, args.exclude, options)
    code = report(checker.check())
    for warning in checker.warnings:
        print(warning)
    return code

def llms(args, parser):
    single = args.paths[0] if len(args.paths) == 1 and os.path.isdir(args.paths[0]) else None
    if not args.output and not single:
        raise UsageError('-o is required unless one folder is listed')
    if not args.title and not single:
        raise UsageError('--title is required unless one folder is listed')
    output = args.output or os.path.join(single, 'llms.txt')
    title = args.title or Path(os.path.abspath(single)).name
    try:
        selection = Selection(args.paths, Filter(args.include, args.exclude))
    except ValueError as e:
        raise UsageError(str(e)) from e
    selection.scanner.root.default_title = title
    text = Llms(selection, output, title, args.summary).text()
    if args.check:
        try:
            with open(output, encoding='utf-8') as f:
                current = f.read()
        except FileNotFoundError:
            current = None
        return report([] if current == text else [f'{output}: out of date, rerun without --check'])
    with open(output, 'w', encoding='utf-8') as f:
        f.write(text)

def ls(args, parser):
    listing = Listing(args.paths, args.include, args.exclude)
    for line in listing.urls() if args.external else listing.files():
        print(line, end='\0' if args.null else '\n')

def stats(args, parser):
    res = Stats(args.paths, args.by, args.include, args.exclude).collect()
    print(json.dumps(res.data(args.top), indent=2, ensure_ascii=False) if args.json else res.report(args.top))

def wrap(args, parser):
    files = Listing(args.paths, args.include, args.exclude).files()
    return report(wrap_files(files, args.width, args.check))

def add_paths(p, help):
    p.add_argument('paths', nargs='+', metavar='path', help=help)

def add_filter(p):
    p.add_argument('--exclude', action='append', default=[], metavar='GLOB',
                   help='skip matching files and folders, besides hidden, node_modules and vendor; repeatable')
    p.add_argument('--include', action='append', default=[], metavar='GLOB',
                   help='take matching ones even if skipped or excluded; repeatable')

def add_build_options(p):
    p.add_argument('--title', help='default: name of the one folder built, or of -o file')
    p.add_argument('--html', action='store_true', help='write HTML only (default: both HTML and markdown)')
    p.add_argument('--md', action='store_true', help='write single markdown file only')
    p.add_argument('-o', '--output',
                   help='folder to write <title>.html and <title>.md in, default: current; '
                        'or file name: out/Wiki writes both, out/Wiki.html or out/Wiki.md one; '
                        'required for several paths')
    p.add_argument('--no-backlinks', action='store_true', help='no "Linked from" list under pages')
    p.add_argument('--no-front-matter', action='store_true', help='no front matter block next to page titles')
    add_filter(p)

BUILD_USAGE = f'[--title TITLE] [--html] [--md] [-o OUTPUT] [--no-backlinks] [--no-front-matter] {FILTER_USAGE}'

def command(commands, name, help, usage):
    return commands.add_parser(name, help=help, prog=f'uwiki {name}', usage=f'%(prog)s <folder|file>... {usage}'.rstrip())

def parser():
    parser = argparse.ArgumentParser(prog='uwiki', usage='%(prog)s <command> <folder|file>... [options]',
                                     description='Markdown utility for Obsidian vaults and other wikis.')
    parser.add_argument('-V', '--version', action='version', version=f'%(prog)s {__version__}')
    commands = parser.add_subparsers(dest='command', required=True, metavar='command')

    p = command(commands, 'build', 'build folders and files of markdown into single HTML and markdown file',
                BUILD_USAGE)
    add_paths(p, 'folders or files to build, e.g. Obsidian vault')
    add_build_options(p)
    p.set_defaults(func=build)

    p = command(commands, 'check', 'check unresolved links and headings, missing images, '
                                   'frontmatter syntax and list numbering',
                f'[--no-folder-links] [--orphans] [--unlinked] [--unlisted] {FILTER_USAGE}')
    add_paths(p, 'folders or files to check')
    p.add_argument('--no-folder-links', action='store_true', help='report links to folders, not files')
    p.add_argument('--orphans', action='store_true',
                   help='report pages no links lead to from the root folder page')
    p.add_argument('--unlinked', action='store_true',
                   help='warn about pages no other page links to, exit code stays as is')
    p.add_argument('--unlisted', action='store_true',
                   help='warn about pages their folder page does not link, exit code stays as is')
    add_filter(p)
    p.set_defaults(func=check)

    p = command(commands, 'llms', 'write llms.txt: every page with its description, one section per folder',
                f'[--title TITLE] [-o FILE] [--summary TEXT] [--check] {FILTER_USAGE}')
    add_paths(p, 'folders or files to list')
    p.add_argument('--title', help='default: name of the one folder listed')
    p.add_argument('-o', '--output', help='default: llms.txt in the one folder listed, links are relative to it')
    p.add_argument('--summary', help='quote under the title, default: description of the folder page '
                                     'of the folder given paths share')
    p.add_argument('--check', action='store_true', help='report if output is out of date instead, exit 1 if so')
    add_filter(p)
    p.set_defaults(func=llms)

    p = command(commands, 'ls', 'list markdown files, or external links in them, one per line',
                f'[--external] [-z] {FILTER_USAGE}')
    add_paths(p, 'folders or files to list')
    p.add_argument('--external', action='store_true',
                   help='list unique http and https links outside front matter and code instead')
    p.add_argument('-z', '--null', action='store_true', help='end lines with NUL, for xargs -0')
    add_filter(p)
    p.set_defaults(func=ls)

    p = command(commands, 'stats', 'count pages, words, headings, list items and links',
                f'[--by folder|KEY] [--top N] [--json] {FILTER_USAGE}')
    add_paths(p, 'folders or files to count')
    p.add_argument('--by', default='folder', metavar='KEY', help='group by folder (default) or frontmatter key')
    p.add_argument('--top', type=int, default=5, help='list N largest pages, default: 5')
    p.add_argument('--json', action='store_true', help='print JSON with every page')
    add_filter(p)
    p.set_defaults(func=stats)

    p = command(commands, 'wrap', 'rewrap long lines of paragraphs and list items in place',
                f'[-w {WIDTH}] [--check] {FILTER_USAGE}')
    add_paths(p, 'folders or files to rewrap')
    p.add_argument('-w', '--width', type=int, default=WIDTH, help=f'default: {WIDTH}, tab counts as 4')
    p.add_argument('--check', action='store_true', help='report lines to rewrap instead, exit 1 if any')
    add_filter(p)
    p.set_defaults(func=wrap)
    parser.commands = commands.choices
    return parser

def main():
    args = parser().parse_args()
    p = parser().commands[args.command]
    for path in getattr(args, 'paths', []):
        if not os.path.exists(path):
            p.error(f'no such file or folder: {path}')
    try:
        code = args.func(args, p)
    except UsageError as e:
        p.error(str(e))
    sys.exit(code or 0)
