"""End-to-end tests: run uwiki.py on fixture vaults and check generated files.

Run with: python3 -m unittest discover tests
"""

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, 'src', 'uwiki.py')
FIXTURES = os.path.join(ROOT, 'tests', 'fixtures')
VAULT = os.path.join(FIXTURES, 'vault')
BROKEN = os.path.join(FIXTURES, 'broken')

HAS_MARKDOWN = importlib.util.find_spec('markdown') is not None


def run(*args, cwd=None, python_args=()):
    return subprocess.run(
        [sys.executable, *python_args, SCRIPT, *args],
        cwd=cwd, capture_output=True, text=True,
    )


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def section(html, id):
    """Returns HTML from page header with given id till next page header."""
    start = html.index(f'id="{id}"')
    end = html.find('class="page"', html.index('>', start))
    return html[start:end if end > 0 else len(html)]


@unittest.skipUnless(HAS_MARKDOWN, 'markdown package is not installed')
class RenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = cls.tmp.name
        res = run(VAULT, '-o', cls.out)
        assert res.returncode == 0, res.stderr
        cls.html = read(os.path.join(cls.out, 'vault.html'))
        cls.md = read(os.path.join(cls.out, 'vault.md'))
        cls.content = cls.html[cls.html.index('class="content"'):cls.html.index('<style>')]

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
        self.assertIn('<h2 id="my-page" class="page">', self.content)
        self.assertIn('<h3 id="my-page--second-section">Second Section</h3>', page)
        self.assertIn('<h4 id="my-page--deeper">Deeper</h4>', page)

    def test_only_page_headers_go_to_toc(self):
        js = read(os.path.join(ROOT, 'src', 'uwiki.js'))
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
        self.assertIn('id="archive-readme" class="page"', self.content)
        self.assertIn('id="projects-alpha-readme" class="page"', self.content)
        root = section(self.content, 'root')
        self.assertIn('<a href="#archive-readme">Readme</a>', root)
        self.assertIn('<a href="#projects-alpha-readme">alpha readme</a>', root)

    def test_ambiguous_link_resolves_to_nearest(self):
        self.assertIn('<a href="#projects-alpha-readme">Readme</a>', section(self.content, 'projects'))

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

    def src(self, name):
        """Attachment path relative to output dir."""
        return quote(os.path.relpath(os.path.join(VAULT, 'attachments', name), self.out).replace(os.sep, '/'))


@unittest.skipUnless(HAS_MARKDOWN, 'markdown package is not installed')
class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_writes_both_to_current_dir(self):
        res = run(VAULT, cwd=self.out)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(sorted(os.listdir(self.out)), ['vault.html', 'vault.md'])

    def test_title_and_output_dir(self):
        res = run(VAULT + '/', 'My Wiki', '-o', os.path.join(self.out, 'sub'))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(sorted(os.listdir(os.path.join(self.out, 'sub'))), ['My Wiki.html', 'My Wiki.md'])
        self.assertIn('<title>My Wiki</title>', read(os.path.join(self.out, 'sub', 'My Wiki.html')))

    def test_html_only(self):
        run(VAULT, '--html', '-o', self.out)
        self.assertEqual(os.listdir(self.out), ['vault.html'])

    def test_md_only(self):
        run(VAULT, '--md', '-o', self.out)
        self.assertEqual(os.listdir(self.out), ['vault.md'])

    def test_bad_arguments(self):
        res = run(os.path.join(self.out, 'missing'))
        self.assertEqual(res.returncode, 2)
        self.assertIn('not a directory', res.stderr)
        res = run(VAULT, 'title', 'extra')
        self.assertEqual(res.returncode, 2)
        res = run()
        self.assertEqual(res.returncode, 2)


class CheckTest(unittest.TestCase):
    def check(self, *paths):
        # hide markdown package: checking must work without it
        code = (
            'import sys, runpy; sys.modules["markdown"] = None; '
            f'sys.argv = {[SCRIPT, "--check-only", *paths]!r}; '
            f'runpy.run_path({SCRIPT!r}, run_name="__main__")'
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

    def test_clean(self):
        code, lines, err = self.check('broken/Good.md', 'broken/Bad.md')
        self.assertNotIn('broken/Good.md', '\n'.join(lines))
        code, lines, err = self.check('vault/Archive')
        self.assertEqual((code, lines), (0, []), err)


if __name__ == '__main__':
    unittest.main()
