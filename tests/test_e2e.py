"""End-to-end tests: run uwiki commands on fixture vaults and check results.

Run with: make test (needs the markdown package)
"""

import json
import os
import re
import subprocess
import sys
import tempfile
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
        self.assertIn('>My Notes</h2>', self.content)
        self.assertIn('>2024 Plans</h2>', self.content)
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
        self.assertIn('<p class="backlinks"><span>Linked from:</span> <a href="#root">vault</a>, '
                      '<a href="#root">vault › Second Section</a>, '
                      '<a href="#my-notes">My Notes › Second Section</a></p>', section(self.content, 'my-page'))
        self.assertIn('<p class="backlinks"><span>Linked from:</span> <a href="#root">vault</a>, '
                      '<a href="#my-notes">My Notes</a></p>', section(self.content, '2024-plans'))
        self.assertIn('Linked from: [vault](#root), [My Notes](#my-notes)\n', self.md)
        self.assertNotIn('backlinks', section(self.content, 'root'))
        self.assertNotIn('backlinks', section(self.content, 'r-d-x'))

    def test_no_backlinks(self):
        with tempfile.TemporaryDirectory() as out:
            res = run('build', VAULT, '--no-backlinks', '-o', out)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertNotIn('<p class="backlinks">', read(os.path.join(out, 'vault.html')))
            self.assertNotIn('Linked from', read(os.path.join(out, 'vault.md')))

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
        self.assertIn('<h2 id="docs" class="page" data-title="Documentation">Documentation</h2>', self.html)
        self.assertIn('class="page" data-title="Guide">Documentation / Guide</h3>', self.html)
        self.assertIn('<h4 id="guide--first-steps-hi-api">First steps: HiAPI</h4>', self.html)
        self.assertIn('data-title="Broken">Documentation / Broken</h3>', self.html)
        self.assertIn('data-title="Use plain links">Documentation / Use plain links</h3>', self.html)
        self.assertIn('<h4 id="decision--context">Context</h4>', self.html)
        self.assertIn('<a href="#docs">Documentation</a>', section(self.html, 'docs'))

    def test_breadcrumbs_show_every_folder(self):
        self.assertIn('data-title="Notes">Projects / Alpha / Notes</h4>', self.vault)

    def test_markdown_links_are_backlinks(self):
        self.assertIn('<p class="backlinks"><span>Linked from:</span> <a href="#root">mdlinks</a>, '
                      '<a href="#root">mdlinks › First steps: HiAPI</a>, <a href="#docs">Documentation</a>, '
                      '<a href="#broken">Broken</a>, <a href="#broken">Broken › First steps: HiAPI</a></p>',
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
        self.assertIn('data-title="Notes">Projects / Alpha / Notes</h4>', html)
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
