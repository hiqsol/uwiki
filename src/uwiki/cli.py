"""Command line: uwiki <command> <folder|file>... [options]."""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from . import __version__
from .build import Build, BuildOptions, UsageError
from .check import Checker, CheckOptions
from .config import Config, ConfigError
from .index import Index
from .lsp import Server
from .llms import Llms
from .ls import Listing
from .stats import Stats
from .watch import RESTARTED, Restart, Watcher, restart
from .mention import link_mentions
from .mv import Move, MoveError
from . import serve as served
from .vault import Filter, Selection, Vaults
from .wrap import WIDTH, wrap_files

FILTER_USAGE = '[--exclude GLOB] [--include GLOB]'

def report(problems):
    for problem in problems:
        print(problem)
    return 1 if problems else 0

def build(args):
    builder = make_build(args)
    problems = builder.run()
    for warning in builder.warnings:
        print(f'warning: {warning}', file=sys.stderr)
    return report(problems)

def make_build(args):
    return Build(args.paths, args.output, args.title, args.html, args.md, args.include, args.exclude,
                 build_options(args))

def given_options(args):
    """Option defaults the vault config gives the command now, for watching to restart on their change."""
    return lambda: config_defaults(parser(), args)

def watch(args):
    Watcher(make_build(args), args.interval, quiet=args.quiet, options=given_options(args)).run()

def serve(args):
    """Builds into a temporary folder unless -o is given, so serving leaves no files behind, HTML only there."""
    tmp = None if args.output else tempfile.TemporaryDirectory(prefix='uwiki-')
    output = args.output or tmp.name + os.sep
    name = None if args.output else Path(Vaults.common(args.paths)).name  # of the file in the temporary folder
    options = build_options(args)
    options.live_reload = True
    options.attachment_base = served.FILES
    options.source_lines = True
    restarted = os.environ.pop(RESTARTED, '')
    port = int(restarted) if restarted.isdigit() and not args.port else args.port  # port 0 picked: the same again
    try:
        html = args.html or not args.output and not args.md
        build = Build(args.paths, output, args.title, html, args.md, args.include, args.exclude, options, name)
        if 'html' not in build.outputs:
            raise UsageError('serve needs HTML output')
        try:
            server = served.Server(build, args.host, port, args.open and not restarted, args.interval, args.quiet,
                                   options=given_options(args))
        except OSError as e:
            sys.exit(f'uwiki serve: cannot listen on {args.host}:{port}: {e.strerror}')
        server.run()
    except Restart as e:
        e.environ[RESTARTED] = str(server.port)
        raise
    finally:
        if tmp:
            tmp.cleanup()

def mv(args):
    try:
        move = Move(args.source, args.target, args.include, args.exclude)
        move.plan()
    except MoveError as e:
        raise UsageError(str(e)) from e
    shown = lambda path: os.path.relpath(path)
    if args.dry_run:
        for line in move.diff(shown):
            print(line)
        return
    move.run()
    print(f'mv {shown(move.source)} {shown(move.target)}')
    for rel in sorted(move.changes):
        print(f'updated links in {shown(move.full(rel))}')

def link(args):
    vaults = Vaults(args.paths, Filter(args.include, args.exclude))
    changes = link_mentions(vaults, args.mentions_ignore, args.mentions_min_length, args.mentions_ignore_case,
                            args.mentions_self_bold, args.width, args.dry_run, tuple(args.mentions_exclude))
    for shown, lines in changes:
        if args.dry_run:
            for n, old, new in lines:
                print(f'{shown}:{n}: {old.strip()}\n{shown}:{n}: {new.strip()}')
        else:
            print(f'linked {len(lines)} lines in {shown}')

def lsp(args):
    Server().serve()
    return 0

def build_options(args):
    return BuildOptions(backlinks=not args.no_backlinks, front_matter=not args.no_front_matter, up=args.up or '')

def check(args):
    options = CheckOptions(folder_links=not args.no_folder_links, orphans=args.orphans,
                           unlisted=args.unlisted, mentions=args.mentions, mentions_ignore=args.mentions_ignore,
                           mentions_min_length=args.mentions_min_length,
                           mentions_ignore_case=args.mentions_ignore_case, mentions_every=args.mentions_every,
                           mentions_self_bold=args.mentions_self_bold,
                           mentions_exclude=tuple(args.mentions_exclude), max_lines=args.max_lines,
                           max_lines_ignore=tuple(args.max_lines_ignore), acyclic=tuple(args.acyclic),
                           stale_days=args.stale_days, stale_date=tuple(args.stale_date),
                           stale_until=args.stale_until)
    checker = Checker(args.paths, args.include, args.exclude, options)
    code = report(checker.check())
    for warning in checker.warnings:
        print(warning)
    return code

def llms(args):
    single = args.paths[0] if len(args.paths) == 1 and os.path.isdir(args.paths[0]) else None
    if not args.output and not single:
        raise UsageError('-o is required unless one folder is listed')
    if not args.title and not single:
        raise UsageError('--title is required unless one folder is listed')
    output = args.output or os.path.join(single, 'llms.txt')
    try:
        selection = Selection(args.paths, Filter(args.include, args.exclude))
    except ValueError as e:
        raise UsageError(str(e)) from e
    title = args.title or selection.index_title() or Path(os.path.abspath(single)).name
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

def index(args):
    index = Index(args.paths, args.include, args.exclude)
    changes = index.changes()
    if index.problems:
        return report(index.problems)
    if args.check:
        return report([line for change in changes for line in Index.diff(*change)])
    for shown, _, text in changes:
        with open(shown, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f'updated {shown}')

def ls(args):
    listing = Listing(args.paths, args.include, args.exclude)
    for line in listing.urls() if args.external else listing.files():
        print(line, end='\0' if args.null else '\n')

def stats(args):
    res = Stats(args.paths, args.by, args.include, args.exclude).collect()
    print(json.dumps(res.data(args.top), indent=2, ensure_ascii=False) if args.json else res.report(args.top))

def wrap(args):
    files = Listing(args.paths, args.include, args.exclude).files()
    return report(wrap_files(files, args.width, args.check))

def add_paths(p, help):
    p.add_argument('paths', nargs='+', metavar='path', help=help)

def add_filter(p):
    p.add_argument('--exclude', action='append', default=[], metavar='GLOB',
                   help='skip matching files and folders, besides hidden, node_modules and vendor; repeatable')
    p.add_argument('--include', action='append', default=[], metavar='GLOB',
                   help='take matching ones even if skipped or excluded; repeatable')

def add_build_options(p, output='current'):
    p.add_argument('--title', help='default: title of the index page of the folder built, else its name, '
                                   'else of -o file; names output files, else the folder does')
    p.add_argument('--html', action='store_true', help='write HTML only (default: both HTML and markdown)')
    p.add_argument('--md', action='store_true', help='write single markdown file only')
    p.add_argument('-o', '--output',
                   help=f'folder to write <title>.html and <title>.md in, default: {output}; '
                        'or file name: out/Wiki writes both, out/Wiki.html or out/Wiki.md one; '
                        'required for several paths')
    p.add_argument('--no-backlinks', action='store_true', help="no backlinks list under pages")
    p.add_argument('--no-front-matter', action='store_true', help='no front matter block next to page titles')
    p.add_argument('--up', metavar='URL', help='link the uWiki logo before the title to this page, '
                                               'e.g. ./ to the index of a site of wikis')
    add_filter(p)

def add_watch_options(p):
    p.add_argument('-q', '--quiet', action='store_true', help='print errors only')
    p.add_argument('--interval', type=float, default=0.5, metavar='SECONDS',
                   help='how often to look for changes, default: 0.5')

BUILD_USAGE = f'[--title TITLE] [--html] [--md] [-o OUTPUT] [--no-backlinks] [--no-front-matter] [--up URL] {FILTER_USAGE}'

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

    p = command(commands, 'watch', 'build, then build again on change of any page, attachment or config',
                f'{BUILD_USAGE} [-q] [--interval SECONDS]')
    add_paths(p, 'folders or files to build')
    add_build_options(p)
    add_watch_options(p)
    p.set_defaults(func=watch)

    p = command(commands, 'serve', 'serve built HTML on localhost, rebuild on change and reload the page',
                f'{BUILD_USAGE} [-p 8000] [--host 127.0.0.1] [--open] [-q] [--interval SECONDS]')
    add_paths(p, 'folders or files to build')
    add_build_options(p, output='temporary one removed on exit')
    p.add_argument('-p', '--port', type=int, default=8000, help='default: 8000, 0 picks a free one')
    p.add_argument('--host', default='127.0.0.1', help='default: 127.0.0.1, 0.0.0.0 serves other hosts too')
    p.add_argument('--open', action='store_true', help='open the page in the browser after the first build')
    add_watch_options(p)
    p.set_defaults(func=serve)

    p = command(commands, 'check', 'check unresolved links and headings, missing images, '
                                   'frontmatter syntax and list numbering',
                f'[--no-folder-links] [--orphans] [--unlisted] [--mentions] [--max-lines N] [--acyclic KEY] '
                f'[--stale-days N --stale-date KEY] [--stale-until KEY] {FILTER_USAGE}')
    add_paths(p, 'folders or files to check')
    p.add_argument('--no-folder-links', action='store_true', help='report links to folders, not files')
    p.add_argument('--orphans', action='store_true',
                   help='report pages no links lead to from the root folder page')
    p.add_argument('--unlisted', action='store_true',
                   help='warn about pages their folder page does not link, exit code stays as is')
    p.add_argument('--mentions', action='store_true',
                   help='warn about the first plain text mention of a page title or alias a page does not link, '
                        'exit code stays as is')
    p.add_argument('--mentions-ignore', action='append', default=[], metavar='TERM',
                   help='title or alias not to warn about; repeatable')
    p.add_argument('--mentions-min-length', type=int, default=3, metavar='N',
                   help='shortest title or alias to warn about, default: 3')
    p.add_argument('--mentions-ignore-case', action='store_true', help='mentions match in any case')
    p.add_argument('--mentions-every', action='store_true',
                   help='warn about every plain text mention, also of pages the page links')
    p.add_argument('--mentions-self-bold', action='store_true',
                   help='warn about a mention of the page itself not in bold, a term rather than a word')
    p.add_argument('--mentions-exclude', action='append', default=[], metavar='GLOB',
                   help='pages mentions leaves alone, glob from the config folder; repeatable')
    p.add_argument('--max-lines', type=int, default=0, metavar='N', help='report pages longer than N lines')
    p.add_argument('--max-lines-ignore', action='append', default=[], metavar='GLOB',
                   help='pages max-lines leaves alone, glob from the config folder; repeatable')
    p.add_argument('--acyclic', action='append', default=[], metavar='KEY',
                   help='report pages a chain of the pages this front matter key names leads back to; repeatable')
    p.add_argument('--stale-days', type=int, default=0, metavar='N',
                   help='warn about pages whose latest --stale-date is more than N days ago, exit code stays as is')
    p.add_argument('--stale-date', action='append', default=[], metavar='KEY',
                   help='front matter date key a page is aged from, dotted for nested ones, the latest wins; '
                        'repeatable')
    p.add_argument('--stale-until', default='', metavar='KEY',
                   help='warn about pages whose date in this front matter key has come, exit code stays as is')
    add_filter(p)
    p.set_defaults(func=check)

    p = command(commands, 'link', 'link every plain text mention of a page title or alias, as check --mentions '
                                  'finds them, rewrap lines it makes too long',
                f'[--dry-run] [-w {WIDTH}] [--mentions-ignore TERM] [--mentions-min-length N] '
                f'[--mentions-ignore-case] [--mentions-self-bold] [--mentions-exclude GLOB] {FILTER_USAGE}')
    add_paths(p, 'folders or files to link mentions in')
    p.add_argument('--dry-run', action='store_true', help='print every changed line instead, before and after')
    p.add_argument('-w', '--width', type=int, default=WIDTH, help=f'rewrap lines longer than this, default: {WIDTH}')
    p.add_argument('--mentions-ignore', action='append', default=[], metavar='TERM',
                   help='title or alias not to link; repeatable')
    p.add_argument('--mentions-min-length', type=int, default=3, metavar='N',
                   help='shortest title or alias to link, default: 3')
    p.add_argument('--mentions-ignore-case', action='store_true', help='mentions match in any case')
    p.add_argument('--mentions-self-bold', action='store_true', help='make mentions of the page itself bold')
    p.add_argument('--mentions-exclude', action='append', default=[], metavar='GLOB',
                   help='pages not to link mentions in, glob from the config folder; repeatable')
    add_filter(p)
    p.set_defaults(func=link)

    p = command(commands, 'llms', 'write llms.txt: every page with its description, one section per folder',
                f'[--title TITLE] [-o FILE] [--summary TEXT] [--check] {FILTER_USAGE}')
    add_paths(p, 'folders or files to list')
    p.add_argument('--title', help='default: title of the index page of the one folder listed, else its name')
    p.add_argument('-o', '--output', help='default: llms.txt in the one folder listed, links are relative to it')
    p.add_argument('--summary', help='quote under the title, default: description of the folder page '
                                     'of the folder given paths share')
    p.add_argument('--check', action='store_true', help='report if output is out of date instead, exit 1 if so')
    add_filter(p)
    p.set_defaults(func=llms)

    p = command(commands, 'index', 'fill <!-- generated: NAME --> blocks of pages with the other pages of their folder',
                f'[--check] {FILTER_USAGE}')
    add_paths(p, 'folders or files with blocks to fill')
    p.add_argument('--check', action='store_true', help='report blocks out of date instead, exit 1 if any')
    add_filter(p)
    p.set_defaults(func=index)

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
    p = commands.add_parser('lsp', prog='uwiki lsp', usage='%(prog)s',
                            help='language server over stdio for editors, in the vault the editor opens')
    p.set_defaults(func=lsp)
    p = commands.add_parser('mv', prog='uwiki mv', usage=f'%(prog)s <from> <to> [--dry-run] {FILTER_USAGE}',
                            help='move or rename a page, folder or attachment, rewriting every link to it')
    p.add_argument('source', metavar='from', help='page, folder or attachment in the vault')
    p.add_argument('target', metavar='to', help='new path, or existing folder to move into')
    p.add_argument('--dry-run', action='store_true', help='print the move and every changed line instead')
    add_filter(p)
    p.set_defaults(func=mv)
    parser.commands = commands.choices
    return parser

TAKES = {'watch': ('build',), 'serve': ('build',), 'link': ('check', 'wrap')}
NOT_OPTIONS = {'paths', 'func', 'command', 'help', 'version'}
CONFIG_ONLY = {'layers', 'code-paths', 'inverse'}  # config keys no command line option takes

def config_defaults(top, args):
    """Defaults of command options from the config of the vault given paths are in."""
    if not getattr(args, 'paths', None):
        return {}
    config = Config.load(Vaults.vault_root(os.path.abspath(args.paths[0]), Vaults.common(args.paths)))
    p = top.commands[args.command]
    dests = {a.dest: a for a in p._actions if a.dest not in NOT_OPTIONS}
    known = {a.dest for sub in top.commands.values() for a in sub._actions}
    res = {}
    for key, value in config.options(args.command, TAKES.get(args.command, ())).items():
        if key in CONFIG_ONLY or isinstance(value, dict):  # a table in a command table configures more than options
            continue
        name = key.replace('-', '_')
        if name in dests:
            action = dests[name]
            if isinstance(action, argparse._AppendAction):
                value = list(value) if isinstance(value, list) else [value]
            res[name] = value
        elif f'no_{name}' in dests and isinstance(value, bool):
            res[f'no_{name}'] = not value
        elif isinstance(config.data.get(args.command), dict) and key in config.data[args.command] \
                or name not in known and f'no_{name}' not in known:
            raise ConfigError(f'{config.path}: unknown option {key} of {args.command}')
    return res

def main():
    top = parser()
    args = top.parse_args()
    p = top.commands[args.command]
    for path in getattr(args, 'paths', []):
        if not os.path.exists(path):
            p.error(f'no such file or folder: {path}')
    try:
        defaults = config_defaults(top, args)
        if defaults:
            p.set_defaults(**defaults)
            args = top.parse_args()
        code = args.func(args)
    except Restart as e:
        restart(e.environ)
    except (UsageError, ConfigError) as e:
        p.error(str(e))
    sys.exit(code or 0)
