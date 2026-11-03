"""End-to-end tests: run uwiki commands on fixture vaults and check results.

Run with: make test (needs the markdown package)
"""

import json
import os
import queue
import shutil
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.parse import quote

import markdown  # noqa: F401 -- required, build tests must not be skipped

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')
FIXTURES = os.path.join(ROOT, 'tests', 'fixtures')
VAULT = os.path.join(FIXTURES, 'vault')
BROKEN = os.path.join(FIXTURES, 'broken')
MDLINKS = os.path.join(FIXTURES, 'mdlinks')
PROJECT = os.path.join(FIXTURES, 'project')
LINKCHECK = os.path.join(FIXTURES, 'linkcheck')
EXTERNAL = os.path.join(FIXTURES, 'external')
ORDER = os.path.join(FIXTURES, 'order')
ITEMS = os.path.join(FIXTURES, 'items')


def run(*args, cwd=None):
    return subprocess.run(
        [sys.executable, '-m', 'uwiki', *args],
        cwd=cwd, capture_output=True, text=True, env={**os.environ, 'PYTHONPATH': SRC},
    )


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def section(html, id):
    """Returns HTML from page header with given id till next page header."""
    start = html.index(f'id="{id}"')
    end = html.find('class="page"', html.index('>', start))
    return html[start:html.rfind('<', 0, end) if end > 0 else len(html)]


class RenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = cls.tmp.name
        res = run('build', VAULT, '-o', cls.out)
        assert res.returncode == 0, res.stderr
        cls.html = read(os.path.join(cls.out, 'vault.html'))
        cls.md = read(os.path.join(cls.out, 'vault.md'))
        cls.content = cls.html[cls.html.index('class="content"'):cls.html.index('<script>')]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def ids(self):
        return re.findall(r'\bid="([^"]+)"', self.content)

    def test_every_link_has_target(self):
        ids = set(self.ids())
        for href in re.findall(r'href="#([^"]*)"', self.content):
            self.assertIn(href, ids)

    def test_ids_are_unique(self):
        ids = self.ids()
        self.assertEqual(len(ids), len(set(ids)))

    def test_page_anchors(self):
        for id in ['root', 'my-page', 'my-notes', '2024-plans', 'projects', 'r-d-x']:
            self.assertIn(f'id="{id}" class="page"', self.content)

    def test_titles(self):
        self.assertIn('>My Notes<details class="backlinks">', self.content)
        self.assertIn('>2024 Plans<details class="backlinks">', self.content)
        self.assertIn('>R&amp;D &lt;x&gt;</h2>', self.content)
        self.assertIn('<title>vault</title>', self.html)

    def test_template_placeholders_in_content_are_kept(self):
        self.assertIn('Literal {style} and {script} stay.', self.content)
        self.assertEqual(self.html.count('<style>'), 1)
        self.assertEqual(self.html.count('<script>'), 1)

    def test_headings_are_shifted_below_page_header(self):
        page = section(self.content, 'my-page')
        self.assertIn('<h2 id="my-page" class="page" data-title="My Page">', self.content)
        self.assertIn('<h3 id="my-page--second-section">Second Section</h3>', page)
        self.assertIn('<h4 id="my-page--deeper">Deeper</h4>', page)

    def test_only_page_headers_go_to_toc(self):
        js = read(os.path.join(SRC, 'uwiki', 'assets', 'uwiki.js'))
        self.assertIn('h2.page', js)
        self.assertNotIn('console.log', js)

    def test_previews_clone_page_for_mouse_only(self):
        js = read(os.path.join(SRC, 'uwiki', 'assets', 'uwiki.js'))
        self.assertIn('cloneNode(true)', js)
        self.assertIn('e.pointerType !== "mouse"', js)
        self.assertNotIn('fetch(', js)
        self.assertNotIn('XMLHttpRequest', js)

    def test_code_is_left_alone(self):
        self.assertIn('<pre><code># not a heading\n[[NotALink]]\n</code></pre>', self.content)
        self.assertIn('<code>[[NotALink]]</code>', self.content)
        self.assertNotIn('not-a-link', self.content)

    def test_links(self):
        root = section(self.content, 'root')
        self.assertIn('<a href="#my-page">My Page</a>', root)
        self.assertIn('<a href="#my-notes">My Notes</a>', root)
        self.assertIn('<a href="#my-page">the page</a>', root)
        self.assertIn('<a href="#my-page--second-section">My Page &gt; Second Section</a>', root)
        self.assertIn('<a href="#root--intro">Intro</a>', root)

    def test_duplicate_names_get_path_anchors(self):
        self.assertIn('id="archive-notes" class="page"', self.content)
        self.assertIn('id="projects-alpha-notes" class="page"', self.content)
        root = section(self.content, 'root')
        self.assertIn('<a href="#archive-notes">Notes</a>', root)
        self.assertIn('<a href="#projects-alpha-notes">alpha readme</a>', root)

    def test_ambiguous_link_resolves_to_nearest(self):
        self.assertIn('<a href="#projects-alpha-notes">Notes</a>', section(self.content, 'projects'))

    def test_folder_page_and_root_named_page(self):
        self.assertIn('Projects folder page', section(self.content, 'projects'))
        self.assertIn('Root named page.', section(self.content, 'root-2'))
        self.assertNotIn('Root named page.', section(self.content, 'root'))

    def test_skipped_files_and_folders(self):
        self.assertNotIn('Ghost', self.content)
        self.assertNotIn('not really', self.content)
        self.assertNotIn('id="empty"', self.content)
        self.assertNotIn('id="attachments"', self.content)

    def test_front_matter_is_stripped(self):
        self.assertNotIn('tags:', self.content)
        self.assertIn('<p>First paragraph is <strong>bold</strong>.</p>', self.content)

    def test_embeds(self):
        notes = section(self.content, 'my-notes')
        self.assertIn(f'<img src="{self.src("pic.png")}" alt="pic.png" />', notes)
        self.assertIn(f'<img src="{self.src("pic.png")}" alt="pic.png" width="100" />', notes)
        self.assertIn(f'<a href="{self.src("doc.pdf")}">doc.pdf</a>', notes)
        self.assertIn(f'<a href="{self.src("doc.pdf")}">the doc</a>', notes)
        embed = re.search(r'<div class="embed">(.*?)</div>', notes, re.DOTALL)[1]
        self.assertIn('<h3>Second Section</h3>', embed)
        self.assertIn('Literal {style}', embed)
        self.assertNotIn('callout', embed.split('<h4>Deeper</h4>')[0])

    def test_self_embed_becomes_link(self):
        plans = section(self.content, '2024-plans')
        self.assertIn('<a href="#2024-plans">2024 Plans</a>', plans)
        self.assertNotIn('class="embed"', plans)

    def test_callouts(self):
        page = section(self.content, 'my-page')
        self.assertIn('<div class="callout callout-note">\n<div class="callout-title">Custom title</div>', page)
        self.assertIn('<details class="callout callout-warning">\n<summary class="callout-title">Warning</summary>', page)
        self.assertIn('<details class="callout callout-tip" open="open">', page)
        self.assertIn('Open with <a href="#my-page--deeper">My Page &gt; Deeper</a></summary>', page)
        self.assertIn('<div class="callout callout-bug">', page)
        self.assertNotIn('[!', page)

    def test_markdown_output(self):
        self.assertIn('<a id="my-page"></a>\n\n## My Page', self.md)
        self.assertIn('<a id="my-page--second-section"></a>\n\n### Second Section', self.md)
        self.assertIn('[My Page > Second Section](#my-page--second-section)', self.md)
        self.assertIn('> [!note] Custom title', self.md)
        self.assertNotIn('tags:', self.md)
        for href in re.findall(r'\]\(#([^)]*)\)', self.md):
            self.assertIn(f'<a id="{href}"></a>', self.md)

    def test_backlinks(self):
        self.assertIn('data-title="My Page">My Page<details class="backlinks"><summary><b>Backlinks (3):</b>'
                      '<span>vault, vault › Second Section, My Notes › Second Section</span></summary>'
                      '<div><a href="#root">vault</a>, <a href="#root">vault › Second Section</a>, '
                      '<a href="#my-notes">My Notes › Second Section</a></div></details><details class="front-matter">',
                      self.content)
        self.assertIn('<details class="backlinks"><summary><b>Backlinks (2):</b><span>vault, My Notes</span>'
                      '</summary><div><a href="#root">vault</a>, <a href="#my-notes">My Notes</a></div></details>',
                      section(self.content, '2024-plans'))
        self.assertIn('Backlinks: [vault](#root), [My Notes](#my-notes)\n', self.md)
        self.assertNotIn('backlinks', section(self.content, 'root'))
        self.assertNotIn('backlinks', section(self.content, 'r-d-x'))

    def test_front_matter_block(self):
        self.assertIn('</details><details class="front-matter"><summary><span>a, b · ignored</span>'
                      '</summary><table><tr><th>tags</th><td>a, b</td></tr><tr><th>summary</th><td>ignored</td></tr>'
                      '</table></details></h2>', self.content)
        self.assertEqual(self.content.count('class="front-matter"'), 1)
        self.assertNotIn('front-matter', self.md)

    def test_front_matter_values(self):
        with tempfile.TemporaryDirectory() as out:
            res = run('build', LINKCHECK, '--html', '-o', out)
            self.assertEqual(res.returncode, 0, res.stderr)
            html = read(os.path.join(out, 'linkcheck.html'))
            res = run('build', VAULT, '--no-front-matter', '-o', out)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertNotIn('<details class="front-matter">', read(os.path.join(out, 'vault.html')))
        self.assertIn('<summary><span>Folded over lines.</span></summary><table><tr><th>title</th><td>Bee</td></tr>'
                      '<tr><th>description</th><td>Folded over lines.</td></tr></table>', html)

    def test_no_backlinks(self):
        with tempfile.TemporaryDirectory() as out:
            res = run('build', VAULT, '--no-backlinks', '-o', out)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertNotIn('<details class="backlinks">', read(os.path.join(out, 'vault.html')))
            self.assertNotIn('Backlinks', read(os.path.join(out, 'vault.md')))

    def src(self, name):
        """Attachment path relative to output dir."""
        return quote(os.path.relpath(os.path.join(VAULT, 'attachments', name), self.out).replace(os.sep, '/'))


class MarkdownLinksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as out:
            res = run('build', MDLINKS, '--html', '-o', out)
            assert res.returncode == 0, res.stderr
            cls.html = read(os.path.join(out, 'mdlinks.html'))
            res = run('build', VAULT, '--html', '-o', out)
            assert res.returncode == 0, res.stderr
            cls.vault = read(os.path.join(out, 'vault.html'))

    def test_relative_links_become_anchors(self):
        root = section(self.html, 'root')
        self.assertIn('<a href="#guide">the guide</a>', root)
        self.assertIn('<a href="#guide--first-steps-hi-api">first steps</a>', root)
        self.assertIn('<a href="#docs">docs</a>', root)
        self.assertIn('<a href="#root--intro">intro</a>', root)
        self.assertIn('<a href="#guide"><code>code text</code></a>', root)
        self.assertIn('<a href="#root--intro">home</a>', section(self.html, 'guide'))

    def test_title_heading_is_replaced_by_page_header(self):
        setup = section(self.html, 'setup')
        self.assertNotIn('<h3', setup)
        self.assertIn('<h4 id="setup--setup-steps">Setup steps</h4>', setup)
        root = section(self.html, 'root')
        self.assertIn('<a href="#setup">setup title</a>', root)
        self.assertIn('<a href="#setup">Setup &gt; Setup</a>', root)

    def test_title_is_leading_heading_else_name(self):
        self.assertIn('<h2 id="docs" class="page" data-title="Documentation">Documentation<details class="backlinks">', self.html)
        self.assertIn('class="page" data-title="Guide">Documentation / Guide<details class="backlinks">', self.html)
        self.assertIn('<h4 id="guide--first-steps-hi-api">First steps: HiAPI</h4>', self.html)
        self.assertIn('data-title="Broken">Documentation / Broken</h3>', self.html)
        self.assertIn('data-title="Use plain links">Documentation / Use plain links</h3>', self.html)
        self.assertIn('<h4 id="decision--context">Context</h4>', self.html)
        self.assertIn('<a href="#docs">Documentation</a>', section(self.html, 'docs'))

    def test_breadcrumbs_show_every_folder(self):
        self.assertIn('data-title="Notes">Projects / Alpha / Notes<details class="backlinks">', self.vault)

    def test_markdown_links_are_backlinks(self):
        self.assertIn('<b>Backlinks (5):</b><span>mdlinks, mdlinks › First steps: HiAPI, Documentation, Broken, '
                      'Broken › First steps: HiAPI</span></summary><div><a href="#root">mdlinks</a>, '
                      '<a href="#root">mdlinks › First steps: HiAPI</a>, <a href="#docs">Documentation</a>, '
                      '<a href="#broken">Broken</a>, <a href="#broken">Broken › First steps: HiAPI</a></div>',
                      section(self.html, 'guide'))

    def test_external_code_and_unresolved_links_are_kept(self):
        self.assertIn('<a href="https://example.com/a.md">site</a>', self.html)
        self.assertIn('<code>[x](docs/Guide.md)</code>', self.html)
        self.assertIn('<a href="../../Outside.md">out</a>', self.html)
        self.assertIn('<a href="#guide">bad heading</a>', self.html)


class ProjectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as out:
            res = run('build', PROJECT, '--html', '-o', out)
            assert res.returncode == 0, res.stderr
            cls.html, cls.stderr = read(os.path.join(out, 'project.html')), res.stderr
            res = run('build', PROJECT, '--html', '-o', out, '--include', 'vendor/**', '--exclude', 'drafts')
            assert res.returncode == 0, res.stderr
            cls.filtered = read(os.path.join(out, 'project.html'))

    def test_readme_is_folder_page_before_index(self):
        self.assertIn('id="root" class="page" data-title="Project">', self.html)
        self.assertIn('id="docs" class="page" data-title="Docs readme">', self.html)
        self.assertIn('data-title="Docs index">Docs readme / Docs index</h3>', self.html)
        self.assertEqual(self.stderr, f'warning: {PROJECT}/docs/index.md: '
                                      'both index.md and README.md in folder, README.md is folder page\n')

    def test_symlink_to_page_is_alias(self):
        self.assertNotIn('id="claude"', self.html)
        self.assertEqual(self.html.count('Agent rules.'), 1)
        root = section(self.html, 'root')
        self.assertEqual(root.count('<a href="#agents">Agents</a>'), 2)
        self.assertIn('<a href="#agents">claude</a>', root)

    def test_symlink_to_folder_is_alias(self):
        self.assertNotIn('id="notes"', self.html)
        self.assertEqual(self.html.count('data-title="Draft"'), 1)
        self.assertIn('<a href="#drafts">through symlink</a>', self.html)

    def test_skip_list_include_and_exclude(self):
        self.assertNotIn('Package', self.html)
        self.assertNotIn('Vendored', self.html)
        self.assertIn('data-title="Draft"', self.html)
        self.assertIn('data-title="Vendored"', self.filtered)
        self.assertNotIn('Package', self.filtered)
        self.assertNotIn('data-title="Draft"', self.filtered)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_writes_both_to_current_dir(self):
        res = run('build', VAULT, cwd=self.out)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(sorted(os.listdir(self.out)), ['vault.html', 'vault.md'])

    def test_title_and_output_dir(self):
        res = run('build', VAULT + '/', '--title', 'My Wiki', '-o', os.path.join(self.out, 'sub') + '/')
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(sorted(os.listdir(os.path.join(self.out, 'sub'))), ['My Wiki.html', 'My Wiki.md'])
        self.assertIn('<title>My Wiki</title>', read(os.path.join(self.out, 'sub', 'My Wiki.html')))

    def test_output_file_name(self):
        res = run('build', VAULT, '-o', os.path.join(self.out, 'sub', 'Wiki'))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(sorted(os.listdir(os.path.join(self.out, 'sub'))), ['Wiki.html', 'Wiki.md'])
        self.assertIn('<title>vault</title>', read(os.path.join(self.out, 'sub', 'Wiki.html')))
        res = run('build', VAULT, '-o', os.path.join(self.out, 'one', 'Wiki.md'))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(os.listdir(os.path.join(self.out, 'one')), ['Wiki.md'])
        res = run('build', VAULT, '--html', '-o', os.path.join(self.out, 'Wiki.md'))
        self.assertEqual(res.returncode, 2)
        self.assertIn('--html and --md do not go with -o', res.stderr)

    def test_several_paths_into_one_output(self):
        res = run('build', VAULT + '/Projects', VAULT + '/Archive', cwd=self.out)
        self.assertEqual(res.returncode, 2)
        self.assertIn('-o is required for several paths', res.stderr)
        res = run('build', VAULT + '/Projects', VAULT + '/Archive', '-o', self.out)
        self.assertEqual(res.returncode, 2)
        self.assertIn('--title is required', res.stderr)
        res = run('build', VAULT + '/Projects', VAULT + '/Archive', '-o', os.path.join(self.out, 'Work'))
        self.assertEqual(res.returncode, 0, res.stderr)
        html = read(os.path.join(self.out, 'Work.html'))
        self.assertIn('<h1 id="root" class="page" data-title="Work">Work</h1>', html)
        self.assertIn('id="projects" class="page"', html)
        self.assertIn('Projects folder page', html)
        self.assertIn('Archive readme.', html)
        self.assertIn('data-title="Notes">Projects / Alpha / Notes<details class="backlinks">', html)
        self.assertNotIn('Root text.', html)
        self.assertNotIn('id="my-page"', html)

    def test_vault_root_keeps_folders(self):
        res = run('build', VAULT + '/Projects/Alpha', '-o', self.out)
        self.assertEqual(res.returncode, 0, res.stderr)
        html = read(os.path.join(self.out, 'Alpha.html'))
        self.assertIn('<h2 id="projects" class="page" data-title="Projects">Projects</h2>', html)
        self.assertNotIn('Projects folder page', html)
        self.assertIn('data-title="Notes">Projects / Alpha / Notes</h4>', html)

    def test_links_outside_built_paths_fail(self):
        res = run('build', 'vault/my notes.md', 'vault/root.md', '-o', os.path.join(self.out, 'Notes'), cwd=FIXTURES)
        self.assertEqual(res.returncode, 1)
        self.assertEqual(res.stdout.splitlines(), [
            'vault/my notes.md:3: embed outside built paths: ![[MyPage#Second Section]]',
            'vault/my notes.md:5: embed outside built paths: ![[2024Plans]]',
        ])
        self.assertEqual(os.listdir(self.out), [])
        res = run('build', 'vault/index.md', 'vault/Archive', '-o', os.path.join(self.out, 'Home'), cwd=FIXTURES)
        self.assertEqual(res.returncode, 1)
        lines = res.stdout.splitlines()
        self.assertEqual(lines[0], 'vault/index.md:1: link outside built paths: [[MyPage]]')
        self.assertNotIn('Archive', res.stdout)

    def test_html_only(self):
        run('build', VAULT, '--html', '-o', self.out)
        self.assertEqual(os.listdir(self.out), ['vault.html'])

    def test_md_only(self):
        run('build', VAULT, '--md', '-o', self.out)
        self.assertEqual(os.listdir(self.out), ['vault.md'])

    def test_bad_arguments(self):
        res = run('build', os.path.join(self.out, 'missing'))
        self.assertEqual(res.returncode, 2)
        self.assertIn('uwiki build: error: no such file or folder', res.stderr)
        res = run('build', VAULT, 'title')
        self.assertEqual(res.returncode, 2)
        res = run('build')
        self.assertEqual(res.returncode, 2)
        res = run('build', VAULT, os.path.join(FIXTURES, 'broken'), '-o', os.path.join(self.out, 'x'))
        self.assertEqual(res.returncode, 2)
        self.assertIn('paths are in different vaults', res.stderr)
        res = run()
        self.assertEqual(res.returncode, 2)

    def test_version(self):
        res = run('--version')
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertRegex(res.stdout, r'^uwiki \d+\.\d+\.\d+\n$')


class CheckTest(unittest.TestCase):
    def check(self, *paths):
        # hide markdown package: checking must work without it
        code = (
            f'import sys, runpy; sys.modules["markdown"] = None; sys.path.insert(0, {SRC!r}); '
            f'sys.argv = {["uwiki", "check", *paths]!r}; '
            'runpy.run_module("uwiki", run_name="__main__")'
        )
        res = subprocess.run([sys.executable, '-c', code], cwd=FIXTURES, capture_output=True, text=True)
        return res.returncode, res.stdout.splitlines(), res.stderr

    def test_vault(self):
        code, lines, err = self.check('vault')
        self.assertEqual((code, lines), (0, []), err)

    def test_checks_agree_with_renderer(self):
        code, lines, err = self.check('subtle')
        self.assertEqual(lines, [
            'subtle/Dots.md:4: unresolved link: [[Nowhere]]',
            'subtle/Links.md:1: unresolved link: [[Wrong/Page]]',
            'subtle/Links.md:1: missing heading: [[Page#NoSuchHeading]]',
            'subtle/Links.md:3: missing heading: [[Sub/Page#Nope]]',
            'subtle/Lists.md:5: list number 3, expected 2',
            'subtle/Lists.md:10: list number 2, expected 1',
        ], err)
        self.assertEqual(code, 1)

    def test_broken(self):
        code, lines, err = self.check('broken')
        self.assertEqual(lines, [
            'broken/Bad.md:2: malformed frontmatter: bad line',
            'broken/Bad.md:5: list number 3, expected 2',
            'broken/Bad.md:7: unresolved link: [[Missing]]',
            'broken/Bad.md:7: missing image: nope.png',
        ], err)
        self.assertEqual(code, 1)

    def test_markdown_links(self):
        code, lines, err = self.check('mdlinks')
        self.assertEqual(lines, [
            'mdlinks/docs/Broken.md:1: link leaves vault: ../../Outside.md',
            'mdlinks/docs/Broken.md:1: unresolved link: Nope.md',
            'mdlinks/docs/Broken.md:1: missing heading: Guide.md#nope',
        ], err)
        self.assertEqual(code, 1)

    def test_index_next_to_readme(self):
        code, lines, err = self.check('project')
        self.assertEqual(lines, [
            'project/docs/index.md:1: both index.md and README.md in folder, README.md is folder page',
        ], err)
        self.assertEqual(code, 1)
        code, lines, err = self.check('project', '--exclude', 'docs/index.md')
        self.assertEqual((code, lines), (0, []), err)

    def test_paths_share_vault(self):
        code, lines, err = self.check('shared/docs', 'shared/ideas', 'shared/Review.md')
        self.assertEqual((code, lines), (0, []), err)

    def test_page_next_to_same_named_folder(self):
        code, lines, err = self.check('shared')
        self.assertEqual((code, lines), (0, []), err)

    def test_relative_links(self):
        code, lines, err = self.check('linkcheck')
        self.assertEqual(lines, [
            'linkcheck/index.md:9: unresolved link: nope.txt',
            'linkcheck/index.md:9: link differs from file name: A.md',
            'linkcheck/index.md:10: absolute link: /a.md',
            'linkcheck/index.md:10: missing heading: a.md#dup-2',
            'linkcheck/index.md:13: unresolved link: sub/nope.md',
            'linkcheck/index.md:15: unresolved link: gone.md',
        ], err)
        self.assertEqual(code, 1)

    def test_page_wins_over_folder_without_page(self):
        code, lines, err = self.check('folderclash', '--orphans')
        self.assertEqual((code, lines), (0, []), err)

    def test_folder_links_and_orphans(self):
        code, lines, err = self.check('linkcheck', '--no-folder-links', '--orphans')
        self.assertIn('linkcheck/index.md:9: folder link: sub/', lines)
        self.assertEqual([line for line in lines if 'orphan' in line],
                         ['linkcheck/orphan.md:1: orphan page: no page links here'])

    def test_unlinked_pages_are_warnings(self):
        code, lines, err = self.check('linkcheck/sub', 'linkcheck/orphan.md', '--unlinked')
        self.assertEqual((code, lines), (0, ['linkcheck/orphan.md:1: warning: no page links here']), err)
        code, lines, err = self.check('linkcheck/sub/c.md', '--orphans')
        self.assertEqual(lines, [], err)

    def test_clean(self):
        code, lines, err = self.check('broken/Good.md', 'broken/Bad.md')
        self.assertNotIn('broken/Good.md', '\n'.join(lines))
        code, lines, err = self.check('vault/Archive')
        self.assertEqual((code, lines), (0, []), err)


class ConfigTest(unittest.TestCase):
    def check(self, *args, cwd=FIXTURES):
        res = run('check', *args, cwd=cwd)
        return res.returncode, res.stdout.splitlines(), res.stderr

    def test_schema(self):
        code, lines, err = self.check('schema')
        self.assertEqual(lines, [
            'schema/Bad.md:2: front matter status: wip, expected one of stub, draft, stable',
            'schema/Bad.md:3: front matter date: soon, expected date',
            'schema/Bad.md:4: front matter tags: x, expected list',
            'schema/Bad.md:5: unknown front matter key: color',
            'schema/None.md:1: missing front matter key: status',
            'schema/docs/Guide.md:1: missing front matter key: owner',
        ], err)
        self.assertEqual(code, 1)

    def test_schema_order(self):
        with tempfile.TemporaryDirectory() as out:
            res = run('build', os.path.join(FIXTURES, 'schema'), '--html', '-o', out)
            self.assertEqual(res.returncode, 0, res.stderr)
            html = read(os.path.join(out, 'schema.html'))
        self.assertIn('<summary><span>draft · 2024-01-02 · a, b</span></summary><table>'
                      '<tr><th>status</th><td>draft</td></tr><tr><th>date</th><td>2024-01-02</td></tr>'
                      '<tr><th>tags</th><td>a, b</td></tr><tr><th>title</th><td>Good: one</td></tr></table>', html)

    def test_option_defaults(self):
        code, lines, err = self.check('schema', '--include', 'drafts')
        self.assertEqual(lines[-2:], [
            'schema/drafts/Draft.md:1: missing front matter key: status',
            'schema/drafts/Draft.md:1: warning: not listed in index.md',
        ], err)
        code, lines, err = self.check('schema/docs/Unlisted.md')
        self.assertEqual((code, lines), (0, []), err)

    def test_pyproject_and_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(os.path.join(tmp, 'Page.md'), '---\ntitle: x\n---\nText.\n')
            write(os.path.join(tmp, 'pyproject.toml'),
                  '[project]\nname = "x"\n[tool.uwiki.schema]\n_required = ["owner"]\nowner = "string"\n')
            code, lines, err = self.check('.', cwd=tmp)
            self.assertEqual(lines, ['./Page.md:2: unknown front matter key: title',
                                     './Page.md:1: missing front matter key: owner'], err)
            write(os.path.join(tmp, 'uwiki.toml'), '[schema]\nowner = "person"\n')
            code, lines, err = self.check('.', cwd=tmp)
            self.assertEqual(code, 2)
            self.assertIn("schema.owner: 'person' is no list of values nor type", err)
            write(os.path.join(tmp, 'uwiki.toml'), '[schema]\n"owner!" = "string"\n')
            code, lines, err = self.check('.', cwd=tmp)
            self.assertEqual(code, 2)
            self.assertIn('schema."owner!": list required keys in _required instead of !', err)
            write(os.path.join(tmp, 'uwiki.toml'), '[schema]\n_required = ["owner"]\n[schema."docs/**"]\nowner = "string"\n')
            code, lines, err = self.check('.', cwd=tmp)
            self.assertEqual(code, 2)
            self.assertIn('schema._required: owner is not in schema', err)
            write(os.path.join(tmp, 'uwiki.toml'), '[check]\nnope = true\n')
            code, lines, err = self.check('.', cwd=tmp)
            self.assertEqual(code, 2)
            self.assertIn('unknown option nope of check', err)
            write(os.path.join(tmp, 'uwiki.toml'), 'title = "Mine"\n[build]\nbacklinks = false\n')
            write(os.path.join(tmp, 'Other.md'), 'See [[Page]].\n')
            self.assertEqual(self.check('.', cwd=tmp)[:2], (0, []))
            res = run('build', '.', '-o', 'out/', cwd=tmp)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(sorted(os.listdir(os.path.join(tmp, 'out'))), ['Mine.html', 'Mine.md'])
            self.assertIn('<title>Mine</title>', read(os.path.join(tmp, 'out', 'Mine.html')))
            self.assertNotIn('Backlinks', read(os.path.join(tmp, 'out', 'Mine.md')))


class AliasTest(unittest.TestCase):
    def test_check_reports_clashes_and_shared_aliases(self):
        res = run('check', 'aliases', cwd=FIXTURES)
        self.assertEqual(res.stdout.splitlines(), [
            'aliases/Clash.md:2: alias Star: Star.md has this name, links lead there',
            'aliases/Clash.md:2: alias Shared: also alias of Sub/Other.md',
            'aliases/Sub/Other.md:2: alias Shared: also alias of Clash.md',
        ], res.stderr)
        self.assertEqual(res.returncode, 1)

    def test_aliases_resolve_and_keep_text(self):
        with tempfile.TemporaryDirectory() as out:
            res = run('build', 'aliases', '-o', out, cwd=FIXTURES)
            self.assertEqual(res.returncode, 0, res.stderr)
            html, md = read(os.path.join(out, 'aliases.html')), read(os.path.join(out, 'aliases.md'))
        self.assertIn('Links [VP](#vice-president), [the VPs](#vice-president), [VP > Vice President](#vice-president), '
                      '[Star](#star), [vp](#vice-president).', md)
        self.assertIn('<h2 id="vice-president" class="page" data-title="Vice President" data-aliases="VP, VPs">', html)
        self.assertIn('<a href="#star">Star</a>', section(html, 'root'))
        self.assertIn('Backlinks: [aliases](#root)', md)
        js = read(os.path.join(SRC, 'uwiki', 'assets', 'uwiki.js'))
        self.assertIn('h.dataset.aliases', js)


class ItemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as out:
            res = run('build', ITEMS, '-o', out)
            assert res.returncode == 0, res.stderr
            cls.html, cls.md = read(os.path.join(out, 'items.html')), read(os.path.join(out, 'items.md'))

    def test_links_to_items(self):
        self.assertIn('Items [Star#2](#star--2), [Star#2.2](#star--2.2), [Star#Light#2](#star--light--2), '
                      '[third](#star--3), [md](#star--3), [#1](#root--1).', self.md)

    def test_anchors_of_first_lists(self):
        self.assertIn('2. <a id="star--2"></a>Second\n\t1. <a id="star--2.1"></a>Nested one', self.md)
        self.assertIn('1. Other list, no anchors', self.md)
        self.assertIn('2. <a id="star--light--2"></a>Light two', self.md)
        self.assertIn('1. code', self.md)
        self.assertIn('<li><a class="item-anchor" id="star--2.2" href="#star--2.2" data-item="2.2"></a>Nested two</li>',
                      self.html)
        self.assertIn('Backlinks: [items › 3](#root), [items › 2](#root), [items › 2.2](#root), '
                      '[items › Light › 2](#root), [items › 9](#root)', self.md)

    def test_check_reports_missing_items(self):
        res = run('check', 'items', cwd=FIXTURES)
        self.assertEqual(res.stdout.splitlines(), [
            'items/index.md:2: missing item: Star.md#9',
            'items/index.md:2: missing item: [[Star#4]]',
            'items/index.md:2: missing item: [[Star#Light#3]]',
        ], res.stderr)


class MentionTest(unittest.TestCase):
    def test_first_plain_mentions_are_warnings(self):
        res = run('check', 'mentions', '--mentions', cwd=FIXTURES)
        self.assertEqual((res.returncode, res.stdout.splitlines()), (0, [
            'mentions/Space.md:1: warning: unlinked mention: Star',
            'mentions/Space.md:1: warning: unlinked mention: Vice President',
            'mentions/Star.md:1: warning: unlinked mention: Space',
            'mentions/Vice President.md:4: warning: unlinked mention: Star',
        ]), res.stderr)

    def test_case_and_config(self):
        res = run('check', 'mentions', '--mentions', '--mentions-ignore-case', '--mentions-min-length', '2',
                  '--mentions-ignore', 'star', cwd=FIXTURES)
        self.assertEqual(res.stdout.splitlines(), [
            'mentions/Space.md:1: warning: unlinked mention: Vice President',
            'mentions/Star.md:1: warning: unlinked mention: Space',
            'mentions/Star.md:5: warning: unlinked mention: Go',
        ], res.stderr)
        with tempfile.TemporaryDirectory() as tmp:
            write(os.path.join(tmp, 'Star.md'), 'Star.\n')
            write(os.path.join(tmp, 'Space.md'), 'Space has a Star and the Moon.\n')
            write(os.path.join(tmp, 'Moon.md'), 'Moon.\n')
            write(os.path.join(tmp, 'uwiki.toml'), '[check]\nmentions = true\nmentions-ignore = ["Moon"]\n')
            res = run('check', '.', cwd=tmp)
        self.assertEqual(res.stdout.splitlines(), ['./Space.md:1: warning: unlinked mention: Star'], res.stderr)

    def test_every_mention_plurals_and_first_letter(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(os.path.join(tmp, 'Class.md'), 'Class.\n')
            write(os.path.join(tmp, 'ForceDiscard.md'), 'Force Discard.\n')
            write(os.path.join(tmp, 'Action.md'), '1. Of the [[Class]], or of several Classes: a class of\n'
                                                   '   **Class**, Force discard\n')
            res = run('check', '.', '--mentions', '--mentions-every', cwd=tmp)
        self.assertEqual(res.stdout.splitlines(), [
            './Action.md:1: warning: unlinked mention: Classes',
            './Action.md:2: warning: unlinked mention: Force discard',
        ], res.stderr)


class LinkMentionTest(unittest.TestCase):
    def test_links_every_mention_and_rewraps(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(os.path.join(tmp, 'Class.md'), 'Class.\n')
            write(os.path.join(tmp, 'ForceDiscard.md'), 'Force Discard.\n')
            write(os.path.join(tmp, 'Component.md'), '---\naliases: [Tile]\n---\n1. **Tile** is a piece\n')
            action = ('1. Of the [[Class]], or of several Classes and their Tiles, `Class` stays, a class too,\n'
                      '   Force discard is a Class\n\n| Class | Force Discard |\n| - | - |\n\n'
                      'A **wrapped\nClass** stays bold.\n')
            write(os.path.join(tmp, 'Action.md'), action)
            res = run('link', '.', '--dry-run', cwd=tmp)
            self.assertEqual(read(os.path.join(tmp, 'Action.md')), action)
            self.assertIn('./Action.md:2: [[ForceDiscard|Force discard]] is a [[Class]]', res.stdout)
            res = run('link', '.', cwd=tmp)
            self.assertEqual(res.stdout, 'linked 3 lines in ./Action.md\n', res.stderr)
            self.assertEqual(read(os.path.join(tmp, 'Action.md')),
                             '1. Of the [[Class]], or of several [[Class]]es and their [[Tile]]s,\n'
                             '   `Class` stays, a class too, [[ForceDiscard|Force discard]] is a\n'
                             '   [[Class]]\n\n'
                             '| [[Class]] | [[ForceDiscard\\|Force Discard]] |\n| - | - |\n\nA **wrapped\nClass** stays bold.\n')
            self.assertEqual(run('check', '.', cwd=tmp).stdout, '')
            with tempfile.TemporaryDirectory() as out:
                res = run('build', tmp, '-o', out, '--md', '--title', 'wiki')
                self.assertIn('| [Class](#class) | [Force Discard](#force-discard) |',
                              read(os.path.join(out, 'wiki.md')), res.stderr)


    def test_own_terms_get_bold(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(os.path.join(tmp, 'Class.md'), '---\naliases: [Kind]\n---\n1. **Class** of a class: Classes, Kinds\n')
            res = run('check', '.', '--mentions', '--mentions-every', '--mentions-self-bold', cwd=tmp)
            self.assertEqual(res.stdout.splitlines(), ['./Class.md:4: warning: own term not bold: Classes',
                                                       './Class.md:4: warning: own term not bold: Kinds'])
            run('link', '.', '--mentions-self-bold', cwd=tmp)
            self.assertEqual(read(os.path.join(tmp, 'Class.md')),
                             '---\naliases: [Kind]\n---\n1. **Class** of a class: **Classes**, **Kinds**\n')

    def test_ignored_name_keeps_its_terms_unlinked(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(os.path.join(tmp, 'Star.md'), 'Star.\n')
            write(os.path.join(tmp, 'Realm.md'), 'Realm.\n')
            write(os.path.join(tmp, 'index.md'), '[[Star]] [[Realm]]: a Star, like in Star Realms, in Star\n'
                                                 '   Realms too, a Realm\n')
            run('link', '.', '--mentions-ignore', 'Star Realms', cwd=tmp)
            self.assertEqual(read(os.path.join(tmp, 'index.md')), '[[Star]] [[Realm]]: a [[Star]], like in Star Realms, '
                                                                   'in Star\n   Realms too, a [[Realm]]\n')

    def test_folder_page_goes_by_its_own_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(os.path.join(tmp, 'Cards', 'Card.md'), 'Card.\n')
            write(os.path.join(tmp, 'Cards', 'Ship.md'), 'Ship.\n')
            write(os.path.join(tmp, 'index.md'), '[[Card]], [[Ship]]: a Card, two Cards.\n')
            res = run('link', '.', cwd=tmp)
            self.assertEqual(read(os.path.join(tmp, 'index.md')), '[[Card]], [[Ship]]: a [[Card]], two [[Card]]s.\n',
                             res.stderr)

class TemplateIdTest(unittest.TestCase):
    def test_page_named_like_template_id_gets_path_anchor(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as out:
            write(os.path.join(tmp, 'index.md'), 'See [[Home]].\n')
            write(os.path.join(tmp, 'rules', 'Home.md'), 'Home.\n')
            res = run('build', tmp, '-o', out, '--title', 'wiki')
            html = read(os.path.join(out, 'wiki.html'))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn('href="#rules-home">Home</a>', html)
        self.assertEqual(html.count('id="home"'), 1)

class AliasItemTest(unittest.TestCase):
    """An alias bold in a list item leads to that item."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        write(os.path.join(self.tmp.name, 'Component.md'),
              '---\naliases: [Tile, Token, Piece]\n---\n1. **Component** is a piece\n2. Components are:\n'
              '\t1. **Card**\n\t2. **Tile**: a piece of the Field\n\t3. **Tokens**: counted\n')
        write(os.path.join(self.tmp.name, 'index.md'), 'See [[Tile]], [[Token]], [[Piece]] and [[Component]].\n')

    def tearDown(self):
        self.tmp.cleanup()

    def test_link_leads_to_item_with_alias_anchor(self):
        with tempfile.TemporaryDirectory() as out:
            res = run('build', self.tmp.name, '-o', out, '--md', '--title', 'wiki')
            md = read(os.path.join(out, 'wiki.md'))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn('See [Tile](#component--2.2), [Token](#component--2.3), [Piece](#component) and '
                      '[Component](#component).', md)
        self.assertIn('2. <a id="component--2.2"></a><a id="component--tile"></a>**Tile**', md)

    def test_lsp_definition_and_hover(self):
        lsp = Lsp(self.tmp.name)
        try:
            lsp.open('index.md')
            res = lsp.at('textDocument/definition', 'index.md', 0, 6)
            self.assertEqual((res['uri'].rsplit('/', 1)[-1], res['range']['start']['line']), ('Component.md', 6))
            res = lsp.at('textDocument/hover', 'index.md', 0, 6)
            self.assertEqual(res['contents']['value'], '**Component#2.2**\n\n2. **Tile**: a piece of the Field')
        finally:
            lsp.close()


class LinkBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as out:
            res = run('build', LINKCHECK, '--md', '-o', out)
            assert res.returncode == 0, res.stderr
            cls.md = read(os.path.join(out, 'linkcheck.md'))

    def test_wrapped_reference_folder_and_titled_links(self):
        self.assertIn('[wrapped\npage](#b) and [ref page][r] and [titled](#a).', self.md)
        self.assertIn('[r]: #b--section\n[bad]: sub/nope.md\n', self.md)
        self.assertIn('[folder](#sub) [file](notes.txt)', self.md)

    def test_heading_anchors_as_hosts_make_them(self):
        self.assertIn('[heading](#a) [repeated](#a--dup) [none](#a) [em](#a--em-u)', self.md)


class LlmsTest(unittest.TestCase):
    def test_pages_with_descriptions_by_folder(self):
        with tempfile.TemporaryDirectory() as out:
            output = os.path.join(out, 'llms.txt')
            res = run('llms', LINKCHECK, '--title', 'Links', '-o', output)
            self.assertEqual(res.returncode, 0, res.stderr)
            rel = os.path.relpath(LINKCHECK, out)
            self.assertEqual(read(output), '\n'.join([
                '# Links', '',
                '> Every kind of relative link.', '',
                '## Home', '',
                f'- [Home]({rel}/index.md): Every kind of relative link.',
                f'- [One -- Two]({rel}/a.md): Quoted: with colon',
                f'- [Orphan]({rel}/orphan.md)', '',
                '## sub/', '',
                f'- [Sub]({rel}/sub/index.md)',
                f'- [C]({rel}/sub/c.md)',
                f'- [Bee]({rel}/sub/b.md): Folded over lines.', '',
            ]))

    def test_check(self):
        with tempfile.TemporaryDirectory() as out:
            output = os.path.join(out, 'llms.txt')
            res = run('llms', LINKCHECK, '-o', output, '--check')
            self.assertEqual((res.returncode, res.stdout), (1, f'{output}: out of date, rerun without --check\n'))
            run('llms', LINKCHECK, '-o', output, '--summary', 'Line one.\nLine two.')
            self.assertIn('# linkcheck\n\n> Line one.\n> Line two.\n\n## Home', read(output))
            res = run('llms', LINKCHECK, '-o', output, '--summary', 'Line one.\nLine two.', '--check')
            self.assertEqual((res.returncode, res.stdout), (0, ''))


class OrderTest(unittest.TestCase):
    ORDER = ['root', 'star', 'ips', 'slot', 'space', 'asteroids', 'moons', 'titan', 'europa',
             'nova', 'comet', 'alone', 'beta']

    def test_build_and_sidebar_follow_links(self):
        with tempfile.TemporaryDirectory() as out:
            res = run('build', ORDER, '-o', out)
            self.assertEqual(res.returncode, 0, res.stderr)
            html, md = read(os.path.join(out, 'order.html')), read(os.path.join(out, 'order.md'))
        self.assertEqual(re.findall(r'id="([^"]+)" class="page"', html), self.ORDER)
        self.assertEqual(re.findall(r'^<a id="([^"-]+)"></a>\n\n#', md, re.MULTILINE), self.ORDER)

    def test_llms_follows_links(self):
        with tempfile.TemporaryDirectory() as out:
            output = os.path.join(out, 'llms.txt')
            res = run('llms', ORDER, '-o', output)
            self.assertEqual(res.returncode, 0, res.stderr)
            titles = re.findall(r'^- \[([^\]]+)\]', read(output), re.MULTILINE)
        self.assertEqual(titles, ['order', 'Star', 'IPS', 'Slot', 'Space', 'Asteroids', 'Nova', 'Comet',
                                  'Alone', 'Beta', 'Moons', 'Titan', 'Europa'])

    def test_unlisted_pages_are_warnings(self):
        res = run('check', 'order', '--unlisted', cwd=FIXTURES)
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertEqual(res.stdout.splitlines(), [
            f'order/{name}.md:1: warning: not listed in index.md'
            for name in ['Alone', 'Asteroids', 'Beta', 'Comet', 'IPS', 'Moons/Europa', 'Moons/index', 'Nova', 'Slot']
        ])


def write(path, text, mode='w'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode, encoding=None if 'b' in mode else 'utf-8') as f:
        f.write(text)


class Background:
    """uwiki command running in background, its output lines read with a timeout."""

    def __init__(self, *args):
        self.proc = subprocess.Popen([sys.executable, '-m', 'uwiki', *args], stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, env={**os.environ, 'PYTHONPATH': SRC})
        self.lines = queue.Queue()
        threading.Thread(target=lambda: [self.lines.put(line) for line in self.proc.stdout], daemon=True).start()

    def line(self, timeout=5):
        return self.lines.get(timeout=timeout).rstrip('\n')

    def quiet(self, seconds):
        """Lines printed within given seconds."""
        time.sleep(seconds)
        res = []
        while not self.lines.empty():
            res.append(self.lines.get().rstrip('\n'))
        return res

    def stop(self):
        self.proc.terminate()
        self.proc.wait(5)
        self.proc.stdout.close()


class WatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = os.path.join(self.tmp.name, 'wiki')
        self.out = os.path.join(self.tmp.name, 'out', 'Wiki.html')
        write(os.path.join(self.vault, 'index.md'), 'See [[A]].\n')
        write(os.path.join(self.vault, 'A.md'), 'Page A.\n')

    def tearDown(self):
        self.tmp.cleanup()

    def test_rebuilds_on_change(self):
        watch = Background('watch', self.vault, '-o', self.out, '--interval', '0.1')
        try:
            self.assertRegex(watch.line(), rf'^\d\d:\d\d:\d\d built 2 pages: {re.escape(self.out)} \(\d+\.\d\ds\)$')
            write(os.path.join(self.vault, 'B.md'), 'Page B.\n')
            write(os.path.join(self.vault, 'attachments', 'pic.png'), 'png')
            self.assertIn('built 3 pages', watch.line())
            self.assertEqual(watch.quiet(0.6), [])
            write(os.path.join(self.vault, 'A.md'), b'\xff\xfe broken', 'wb')
            self.assertIn('error: Error reading', watch.line())
            self.assertIn('build failed, last good output stays', watch.line())
            self.assertIn('Page A.', read(self.out))
            os.rename(os.path.join(self.vault, 'A.md'), os.path.join(self.vault, 'C.md'))
            write(os.path.join(self.vault, 'C.md'), 'Page C.\n')
            self.assertIn('built 3 pages', watch.line())
            self.assertIn('Page C.', read(self.out))
        finally:
            watch.stop()

    def test_quiet_prints_errors_only(self):
        watch = Background('watch', self.vault, '-o', self.out, '--interval', '0.1', '-q')
        try:
            time.sleep(0.5)
            self.assertTrue(os.path.exists(self.out))
            write(os.path.join(self.vault, 'A.md'), b'\xff', 'wb')
            self.assertIn('error: Error reading', watch.line())
            self.assertEqual(watch.quiet(0.5), [])
        finally:
            watch.stop()


class ServeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = os.path.join(self.tmp.name, 'wiki')
        write(os.path.join(self.vault, 'index.md'), 'See [[A]] ![[pic.png]].\n')
        write(os.path.join(self.vault, 'A.md'), 'Page A.\n')
        write(os.path.join(self.vault, 'pic.png'), 'png')

    def tearDown(self):
        self.tmp.cleanup()

    def get(self, url):
        from urllib.request import urlopen
        with urlopen(url, timeout=5) as res:
            return res.status, res.geturl(), res.read().decode()

    def test_serves_rebuilds_and_cleans_up(self):
        from urllib.error import HTTPError
        serve = Background('serve', self.vault, '-p', '0', '--interval', '0.1')
        try:
            url = re.fullmatch(r'serving (http://127\.0\.0\.1:\d+/wiki\.html)', serve.line())[1]
            built = re.search(r'built 2 pages: (\S+)/wiki\.html, ', serve.line())
            outdir = built[1]
            self.assertTrue(outdir.startswith(tempfile.gettempdir()))
            status, _, html = self.get(url)
            build_id = self.get(url.replace('wiki.html', '__uwiki/build'))[2]
            self.assertIn(f'var BUILD = "{build_id}";', html)
            self.assertIn('<img src="/__uwiki/files/pic.png" alt="pic.png" />', html)
            self.assertEqual(self.get(url.replace('wiki.html', '__uwiki/files/pic.png'))[2], 'png')
            with self.assertRaises(HTTPError):
                self.get(url.replace('wiki.html', '__uwiki/files/A.md'))
            self.assertEqual(self.get(url.replace('wiki.html', ''))[1], url)
            write(os.path.join(self.vault, 'A.md'), 'Page A changed.\n')
            self.assertIn('built 2 pages', serve.line())
            self.assertNotEqual(self.get(url.replace('wiki.html', '__uwiki/build'))[2], build_id)
            self.assertIn('Page A changed.', self.get(url)[2])
        finally:
            serve.stop()
        self.assertFalse(os.path.exists(outdir))

    def test_build_output_has_no_reload(self):
        with tempfile.TemporaryDirectory() as out:
            run('build', self.vault, '-o', out)
            html = read(os.path.join(out, 'wiki.html'))
        self.assertNotIn('__uwiki', html)
        self.assertNotIn('uwiki-reload', html)


class MoveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        for name in ['vault', 'mdlinks']:
            shutil.copytree(os.path.join(FIXTURES, name), os.path.join(self.tmp.name, name), symlinks=True)

    def tearDown(self):
        self.tmp.cleanup()

    def run_in(self, *args):
        return run(*args, cwd=self.tmp.name)

    def test_dry_run_prints_move_and_changed_lines(self):
        res = self.run_in('mv', 'vault/MyPage.md', 'vault/Archive/Renamed.md', '--dry-run')
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.splitlines()[:3], [
            'mv vault/MyPage.md vault/Archive/Renamed.md',
            'vault/Archive/Renamed.md:24: - > [!tip]+ Open with [[MyPage#Deeper]]',
            'vault/Archive/Renamed.md:24: + > [!tip]+ Open with [[Renamed#Deeper]]',
        ])
        self.assertIn('vault/my notes.md:3: + ![[Renamed#Second Section]]', res.stdout.splitlines())
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, 'vault', 'MyPage.md')))

    def test_check_passes_after_moves(self):
        self.assertEqual(self.run_in('check', 'vault').returncode, 0)
        for args in [('vault/MyPage.md', 'vault/Archive/Renamed.md'), ('vault/Projects', 'vault/Work'),
                     ('vault/attachments/pic.png', 'vault/images/pic.png'), ('vault/my notes.md', 'vault/Work')]:
            res = self.run_in('mv', *args)
            self.assertEqual(res.returncode, 0, res.stderr)
        res = self.run_in('check', 'vault')
        self.assertEqual((res.returncode, res.stdout), (0, ''))
        index = read(os.path.join(self.tmp.name, 'vault', 'index.md'))
        self.assertIn('See [[Renamed]], [[my notes]], [[2024Plans]] and [[Project]].', index)
        self.assertIn('[[Work/Alpha/Notes|alpha readme]]', index)
        self.assertIn('![[pic.png]]', read(os.path.join(self.tmp.name, 'vault', 'Work', 'my notes.md')))

    def test_links_that_would_lead_elsewhere_change(self):
        res = self.run_in('mv', 'vault/Archive/Notes.md', 'vault/Projects/Notes.md', '--dry-run')
        self.assertEqual(res.stdout.splitlines()[1:], [
            'vault/Projects/Project.md:1: - Projects folder page, see [[Notes]].',
            'vault/Projects/Project.md:1: + Projects folder page, see [[Alpha/Notes]].',
            'vault/index.md:3: - Path links [[Archive/Notes]] and [[Projects/Alpha/Notes|alpha readme]].',
            'vault/index.md:3: + Path links [[Projects/Notes]] and [[Projects/Alpha/Notes|alpha readme]].',
        ])

    def test_markdown_links_follow_and_moved_pages_are_fixed(self):
        res = self.run_in('mv', 'mdlinks/docs/Guide.md', 'mdlinks/Guide.md')
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn('Back [home](index.md#intro).', read(os.path.join(self.tmp.name, 'mdlinks', 'Guide.md')))
        index = read(os.path.join(self.tmp.name, 'mdlinks', 'index.md'))
        self.assertIn('See [the guide](Guide.md), [first steps](Guide.md#first-steps-hiapi)', index)
        self.assertIn('Code `[x](docs/Guide.md)` stays', index)
        res = self.run_in('mv', 'mdlinks/docs', 'mdlinks/manual')
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn('and [docs](manual/index.md).', read(os.path.join(self.tmp.name, 'mdlinks', 'index.md')))
        self.assertIn('[bad heading](../Guide.md#nope)',
                      read(os.path.join(self.tmp.name, 'mdlinks', 'manual', 'Broken.md')))

    def test_paths_in_inline_code_and_link_text_follow(self):
        root = os.path.join(self.tmp.name, 'mdlinks')
        with open(os.path.join(root, 'Paths.md'), 'w', encoding='utf-8') as f:
            f.write('See `docs/`, `docs/Guide.md`, [docs/Setup.md](docs/Setup.md) and [`docs/`](docs/index.md).\n'
                    'Stay: `index.md`, `docs/Nope.md`, `[x](docs/Guide.md)`, [the docs](docs/index.md).\n'
                    '```\ndocs/Guide.md\n```\n')
        with open(os.path.join(root, 'docs', 'Paths.md'), 'w', encoding='utf-8') as f:
            f.write('Next to `./Guide.md`, up at `../index.md`.\n')
        os.makedirs(os.path.join(root, 'out'))
        for name, text in [('uwiki.toml', 'exclude = ["out"]\n'), ('out/Built.md', 'Built `docs/Guide.md`.\n')]:
            with open(os.path.join(root, name), 'w', encoding='utf-8') as f:
                f.write(text)
        res = run('mv', 'docs', 'manual', cwd=root)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(read(os.path.join(root, 'Paths.md')),
                         'See `manual/`, `manual/Guide.md`, [manual/Setup.md](manual/Setup.md) and '
                         '[`manual/`](manual/index.md).\n'
                         'Stay: `index.md`, `docs/Nope.md`, `[x](docs/Guide.md)`, [the docs](manual/index.md).\n'
                         '```\ndocs/Guide.md\n```\n')
        self.assertEqual(read(os.path.join(root, 'manual', 'Paths.md')), 'Next to `./Guide.md`, up at `../index.md`.\n')
        self.assertEqual(read(os.path.join(root, 'out', 'Built.md')), 'Built `docs/Guide.md`.\n')
        res = run('mv', 'manual/Paths.md', 'Deep/Paths.md', cwd=root)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(read(os.path.join(root, 'Deep', 'Paths.md')),
                         'Next to `../manual/Guide.md`, up at `../index.md`.\n')

    def test_git_mv_and_errors(self):
        vault = os.path.join(self.tmp.name, 'vault')
        git = lambda *args: subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *args], cwd=vault,
                                           capture_output=True, text=True, check=True).stdout
        git('init', '-q')
        git('add', '.')
        git('commit', '-qm', 'init')
        res = run('mv', 'root.md', 'Base.md', cwd=vault)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn('R  root.md -> Base.md', git('status', '--porcelain'))
        res = run('mv', 'Base.md', 'index.md', cwd=vault)
        self.assertEqual(res.returncode, 2)
        self.assertIn('already exists', res.stderr)
        res = run('mv', 'Base.md', 'Base.txt', cwd=vault)
        self.assertEqual(res.returncode, 2)
        self.assertIn('keeps its .md extension', res.stderr)


class Lsp:
    """Language server in a subprocess, its replies by id and diagnostics by file name."""

    def __init__(self, root, encodings=()):
        self.proc = subprocess.Popen([sys.executable, '-m', 'uwiki', 'lsp'], cwd=root, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, env={**os.environ, 'PYTHONPATH': SRC})
        self.root, self.id, self.diagnostics = root, 0, {}
        self.request('initialize', {'rootUri': 'file://' + root,
                                    'capabilities': {'general': {'positionEncodings': list(encodings)}}})
        self.notify('initialized', {})

    def write(self, message):
        data = json.dumps({'jsonrpc': '2.0', **message}).encode()
        self.proc.stdin.write(b'Content-Length: %d\r\n\r\n' % len(data) + data)
        self.proc.stdin.flush()

    def read(self):
        length = None
        while True:
            line = self.proc.stdout.readline().strip()
            if not line:
                break
            length = int(line.split(b':')[1])
        return json.loads(self.proc.stdout.read(length))

    def notify(self, method, params):
        self.write({'method': method, 'params': params})

    def request(self, method, params):
        self.id += 1
        self.write({'id': self.id, 'method': method, 'params': params})
        while True:
            message = self.read()
            if message.get('method') == 'textDocument/publishDiagnostics':
                self.diagnostics[message['params']['uri'].rsplit('/', 1)[-1]] = message['params']['diagnostics']
            elif message.get('id') == self.id:
                return message.get('result')

    def uri(self, name):
        return 'file://' + os.path.join(self.root, name)

    def open(self, name, text=None):
        text = read(os.path.join(self.root, name)) if text is None else text
        self.notify('textDocument/didOpen', {'textDocument': {'uri': self.uri(name), 'languageId': 'markdown',
                                                              'version': 1, 'text': text}})

    def at(self, method, name, line, character, **params):
        return self.request(method, {'textDocument': {'uri': self.uri(name)},
                                     'position': {'line': line, 'character': character}, **params})

    def close(self):
        self.request('shutdown', {})
        self.notify('exit', {})
        self.proc.wait(timeout=10)
        self.proc.stdout.close()
        self.proc.stdin.close()


class LspTest(unittest.TestCase):
    def setUp(self):
        self.lsp = Lsp(ITEMS)
        self.lsp.open('index.md')
        self.index = read(os.path.join(ITEMS, 'index.md')).splitlines()

    def tearDown(self):
        self.lsp.close()

    def col(self, n, text):
        return self.index[n].index(text) + 2

    def definition(self, n, text):
        res = self.lsp.at('textDocument/definition', 'index.md', n, self.col(n, text))
        return res and (res['uri'].rsplit('/', 1)[-1], res['range']['start']['line'])

    def test_definition_leads_to_page_heading_and_item(self):
        self.assertEqual(self.definition(0, '[[Star#2.2]]'), ('Star.md', 5))
        self.assertEqual(self.definition(0, '[[Star#Light#2]]'), ('Star.md', 19))
        self.assertEqual(self.definition(0, '[md](Star.md#3)'), ('Star.md', 6))
        self.assertEqual(self.definition(0, '[[#1]]'), ('index.md', 3))
        self.assertIsNone(self.lsp.at('textDocument/definition', 'index.md', 0, 0))

    def test_hover_shows_item_with_nested_ones(self):
        res = self.lsp.at('textDocument/hover', 'index.md', 0, self.col(0, '[[Star#2]]'))
        self.assertEqual(res['contents']['value'], '**Star#2**\n\n2. Second\n\t1. Nested one\n\t2. Nested two')

    def test_completion_of_names_headings_and_items(self):
        self.lsp.open('New.md', '[[St\n[[Star#\n[[Star#Light#')
        labels = lambda n, c: [i['label'] for i in self.lsp.at('textDocument/completion', 'New.md', n, c)]
        self.assertIn('Star', labels(0, 4))
        self.assertEqual(labels(1, 7), ['Star', '1', '2', '2.1', '2.2', '3', 'Light'])
        self.assertEqual(labels(2, 13), ['1', '2'])

    def test_references_of_item_line(self):
        self.lsp.open('Star.md')
        res = self.lsp.at('textDocument/references', 'Star.md', 3, 0, context={'includeDeclaration': False})
        self.assertEqual([(r['uri'].rsplit('/', 1)[-1], r['range']['start']['line']) for r in res],
                         [('index.md', 0)])

    def test_outline_nests_items_under_headings(self):
        self.lsp.open('Star.md')
        res = self.lsp.request('textDocument/documentSymbol', {'textDocument': {'uri': self.lsp.uri('Star.md')}})
        tree = lambda symbols: [(s['name'].split(' ')[0], tree(s['children'])) for s in symbols]
        self.assertEqual(tree(res), [('Star', [('1', []), ('2', [('2.1', []), ('2.2', [])]), ('3', []),
                                               ('Light', [('1', []), ('2', [])])])])

    def test_diagnostics_of_check(self):
        self.lsp.request('shutdown', {})
        problems = [(d['range']['start']['line'], d['message']) for d in self.lsp.diagnostics['index.md']]
        self.assertEqual(problems, [(1, 'missing item: Star.md#9'), (1, 'missing item: [[Star#4]]'),
                                    (1, 'missing item: [[Star#Light#3]]')])

    def test_utf16_positions(self):
        self.lsp.open('New.md', '😀 [[Star#3]]')
        res = self.lsp.at('textDocument/definition', 'New.md', 0, 4)
        self.assertEqual(res['range']['start']['line'], 6)
        hover = self.lsp.at('textDocument/hover', 'New.md', 0, 4)
        self.assertEqual(hover['range']['start']['character'], 3)


class LsTest(unittest.TestCase):
    def ls(self, *args):
        res = run('ls', *args, cwd=FIXTURES)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout

    def test_files(self):
        self.assertEqual(self.ls('external'), 'external/index.md\nexternal/my page.md\n')
        self.assertEqual(self.ls('external', '-z'), 'external/index.md\0external/my page.md\0')
        self.assertEqual(self.ls('external', '--exclude', 'index.md'), 'external/my page.md\n')

    def test_files_skip_symlinks_and_skip_list(self):
        self.assertEqual(self.ls('project').splitlines(), [
            'project/AGENTS.md', 'project/README.md', 'project/docs/README.md',
            'project/docs/index.md', 'project/drafts/Draft.md',
        ])

    def test_external_links_outside_code(self):
        self.assertEqual(self.ls('external', '--external').splitlines(), [
            'http://example.org/f?q=1&r=2#frag',
            'https://en.wikipedia.org/wiki/Foo_(bar)',
            'https://example.com/a',
            'https://example.com/b',
            'https://example.com/c',
            'https://example.com/d',
            'https://example.com/e',
        ])
        self.assertEqual(self.ls('external/my page.md', '--external'), 'https://example.com/c\n')


class StatsTest(unittest.TestCase):
    def stats(self, *args):
        res = run('stats', *args, cwd=FIXTURES)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout

    def test_counts(self):
        data = json.loads(self.stats('vault', '--json'))
        pages = {p['path']: p for p in data['pages']}
        page = pages['vault/MyPage.md']
        self.assertEqual((page['headings'], page['items'], page['links']), (2, 1, 2))
        self.assertEqual(page['meta'], {'tags': '[a, b]', 'summary': 'ignored'})
        notes = pages['vault/my notes.md']
        self.assertEqual((notes['links'], notes['images']), (4, 2))
        self.assertEqual(data['total']['pages'], 9)
        self.assertEqual(data['total']['words'], sum(p['words'] for p in data['pages']))

    def test_orphans_and_folder_pages(self):
        data = json.loads(self.stats('vault', '--json'))
        self.assertEqual(data['orphans'], ['vault/R&D <x>.md', 'vault/root.md'])
        self.assertEqual(sorted(data['groups']), ['vault', 'vault/Archive', 'vault/Projects', 'vault/Projects/Alpha'])

    def test_markdown_links_count_for_orphans(self):
        data = json.loads(self.stats('linkcheck', '--json'))
        self.assertEqual(data['orphans'], ['linkcheck/orphan.md'])

    def test_group_by_frontmatter_key(self):
        data = json.loads(self.stats('vault', '--by', 'tags', '--json'))
        self.assertEqual(data['groups']['[a, b]']['pages'], 1)
        self.assertEqual(data['groups']['-']['pages'], 8)

    def test_report(self):
        lines = self.stats('vault', '--top', '1').splitlines()
        self.assertEqual(lines[0].split(), ['folder', 'pages', 'words', 'lines', 'headings', 'items',
                                            'links', 'external', 'images'])
        self.assertEqual(lines[5].split()[:2], ['total', '9'])
        self.assertEqual(lines[7:9], ['largest:', '      33  vault/MyPage.md'])


class WrapTest(unittest.TestCase):
    TEXT = (
        '---\ntitle: a very long frontmatter line that is not wrapped at all, never\n---\n'
        '1. a long numbered rule with [[Some Link]] and `inline code` that goes beyond\n'
        '\t- nested\n'
        '| table | row that is long enough to exceed the width of seventy columns |\n'
    )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.tmp.name, 'Page.md')
        with open(self.file, 'w', encoding='utf-8') as f:
            f.write(self.TEXT)

    def tearDown(self):
        self.tmp.cleanup()

    def test_check_reports_and_keeps_file(self):
        res = run('wrap', '--check', '-w', '40', self.file)
        self.assertEqual(res.returncode, 1)
        self.assertEqual(res.stdout, f'{self.file}:4: longer than 40 columns\n')
        self.assertEqual(read(self.file), self.TEXT)

    def test_wrap(self):
        res = run('wrap', '-w', '40', self.file)
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = read(self.file).splitlines()
        self.assertEqual(lines[3:7], [
            '1. a long numbered rule with',
            '   [[Some Link]] and `inline code` that',
            '   goes beyond',
            '\t- nested',
        ])
        self.assertEqual(lines[1], self.TEXT.splitlines()[1])
        self.assertEqual(lines[-1], self.TEXT.splitlines()[-1])
        self.assertEqual(run('wrap', '--check', '-w', '40', self.file).returncode, 0)

    def test_folders_with_filters(self):
        os.makedirs(os.path.join(self.tmp.name, 'node_modules'))
        os.makedirs(os.path.join(self.tmp.name, 'sub'))
        for name in ['node_modules/Skip.md', 'sub/Other.md']:
            with open(os.path.join(self.tmp.name, name), 'w', encoding='utf-8') as f:
                f.write(self.TEXT)
        res = run('wrap', '--check', '-w', '40', '.', '--exclude', 'Other.md', cwd=self.tmp.name)
        self.assertEqual((res.returncode, res.stdout), (1, './Page.md:4: longer than 40 columns\n'))
        res = run('wrap', '-w', '40', '.', cwd=self.tmp.name)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotEqual(read(os.path.join(self.tmp.name, 'sub', 'Other.md')), self.TEXT)
        self.assertEqual(read(os.path.join(self.tmp.name, 'node_modules', 'Skip.md')), self.TEXT)

    def test_unbreakable_line_not_reported(self):
        text = ('1. [Rules\n'
                '   pdf](https://example.com/a/very/long/path/to/the/rules.pdf).\n'
                '   `/a/very/long/path/that/inline/code/never/splits`\n')
        with open(self.file, 'w', encoding='utf-8') as f:
            f.write(text)
        res = run('wrap', '--check', '-w', '40', self.file)
        self.assertEqual(res.returncode, 0, res.stdout)
        run('wrap', '-w', '40', self.file)
        self.assertEqual(read(self.file), text)


if __name__ == '__main__':
    unittest.main()
