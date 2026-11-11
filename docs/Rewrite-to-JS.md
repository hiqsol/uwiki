# Rewrite to JS or TS

Should uwiki be rewritten from Python into JS? Analyses of 2026-11-04 and 2026-11-11, measured on 8bitgalaxy:
229 built pages, 385 KB of markdown, 7.5k links, Chromium at 4x CPU throttle unless told otherwise.

**Verdict: not now, maybe never.** The one strong argument holds only if the page is going to render markdown
or resolve links itself, and that makes the page bigger over the network and slower to open.
What is slow is the work the page does at load and an uncached build, neither is about the language.

## Measured

- Code: 4.2k lines of Python, 2.1k of JS and 1.3k of CSS in the page, one dependency `markdown-it-py`.
- Build 3.3s: each page is converted about 5 times (1129 reads for 229 pages), link lookup is not cached
  (56k calls, 2.5s of 8.2s under the profiler). Algorithmic, fixed by "Page parsed once" and a cache.
- HTML 936 KB, 200 KB gzipped: text 324K, `href`s 145K, item anchors 93K, heading ids 62K, data JSON 84K
  (backlinks 45K), JS 82K, CSS 33K. Size is not what makes it slow: parsing all of it takes 460 ms.
- Load: 1.19s till the page is ready, 600 ms of it the page JS, with a saved `?q=` filter 2.4s laying out
  every page, typing a filter 1.5s. Not drawing pages found, building aside tables on unfold and the search
  index when idle made it 0.98s, 1.2s and 0.26s; parsing the HTML is about half of what is left.
- Rendering in the page, precomputing on build: the numbers are computed already, what costs is building
  elements and layout. A prebuilt search index is a second copy of all text, 300 KB, to save 70 ms once.

## Pros

1. **One language for the CLI and the page**, the real argument: the page could resolve links and render
   markdown for live editing, comments and `serve` without rebuilding, the CLI and the page would share one model.
   Also server rendering what the page re-renders, as the sidebar: one function, not Python matching JS markup.
2. **`markdown-it` is the original**, `render.py` ports almost line for line.
3. **Speed**: V8 likely 3-10x on regex and string work, but the build is slow by algorithm, not language.
4. **8bitgalaxy** is a Node project, could pin uwiki as a devDependency.

## Cons

1. **Shipping markdown and rendering it in the page is no gain.** Prepared markdown is 420K against 725K
   of HTML, but gzipped 126K against 152K, and markdown-it alone adds 45K: bigger over the network,
   about 20% smaller as a local file. Rendering takes 340 ms plus 100 ms inserting, nothing shows before it
   is done, while HTML paints as it streams. Rendering pages lazily breaks Ctrl+F and deep links.
2. **Two models again**: the page renderer needs anchors, item numbers and problem lines ported to JS.
3. **The standard library rule breaks**: no TOML, unified diff or subcommand help in Node.
4. **Regex traps**: JS `\w` and `\b` are ASCII only, about 28 uses would quietly break Cyrillic names.
5. **No build step is not quite true**: the page is one file with inline script, ES modules need
   joining with `import` and `export` stripped.
6. **Tests, install and release** all rewritten.

## How to decide

Will the page ever render markdown itself, for editing? Until then stay in Python: parse each page once,
cache lookups, make the page do less at load. If yes, port everything, never half: finish "Page parsed once"
first, write plain ES modules with JSDoc and `// @ts-check`, Node with `smol-toml`, add Cyrillic fixtures first,
keep the Python suite as the reference and diff both outputs on 8bitgalaxy till they match.
