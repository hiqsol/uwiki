# Rewrite to JS or TS

Should uwiki be rewritten from Python into JS or TS? Analysis of 2026-11-04.

**Verdict: not now, and maybe never.** There is one strong argument, and it holds only if the HTML page
is going to resolve links and render markdown itself. Otherwise the rewrite costs weeks and gives nothing
that Python cannot give more cheaply.

## Measured

- Code: 4.2k lines of Python in 17 modules, 1.4k lines of JS and 850 of CSS already running in the page,
  a 1.6k-line end-to-end suite of 125 tests. The only dependency is `markdown-it-py`.
- Pace: 131 commits, about 100 of them in the last 6 days.
- 8bitgalaxy, 537 pages and 363k words, with uwiki 0.13.0: `build` 3.0s, `check` 1.2s, `stats` 0.6s,
  startup 0.14s.
- Profile of `build`: the biggest cost is link lookup, `vault.named` and `lookup` called 54k times,
  building `Path` objects and sorting on each call, about 2.2s of 7.6s under the profiler.
  It is CPython overhead that caching fixes, not a limit of the language.

## Pros

1. **One language for the CLI and the page.** The real argument. [Backlog](Backlog.md) makes the page
   a reading IDE where everything runs in the page. Today Python works everything out ahead of time and packs it
   into the JSON data of the page, so the page and the CLI hold two models of the same thing.
   In JS the link resolver, front matter and renderer could run in the browser too: live re-rendering in `serve`,
   hover previews that resolve links, later editing and comments.
2. **`markdown-it` is the original, `markdown-it-py` its faithful port.** The plugin API is nearly the same
   (`core.ruler.before`, tokens, `attrSet`), `render.py` ports almost line for line and renders the same output.
3. **Speed.** V8 is likely 3–10x faster on this regex and string heavy work. A bonus, not a reason (see cons).
4. **Distribution for 8bitgalaxy.** That vault is already a Vite and TS project with a `package.json`,
   an npm package lets it pin its uwiki version as a devDependency instead of needing a released uwiki from mise.
5. **Types and editor tooling.** TS or JSDoc checked by `tsc` helps the Page, Folder and Link model.
   LSP positions are UTF-16 code units by default, as JS strings are.

## Cons

1. **Timing.** The next backlog item, "Page parsed once", restructures the core into a cached record per page
   with one `resolve_link`. Porting first ports code about to be restructured, and features stop until it is done.
2. **The standard library rule breaks.** Python's standard library gives `tomllib`, `argparse` with subcommand help,
   `difflib` for `index --check`, `webbrowser` and `http.server`. Node has no TOML parser and no unified diff,
   `util.parseArgs` has no subcommands or help. Either dependencies or hand-written code.
   Bun has TOML built in and Deno has `@std/toml`, either ties uwiki to that runtime.
3. **Regex traps that fail silently.** Python `\w`, `\b` and `\s` match Unicode by default,
   JS `\w` and `\b` match only ASCII even with the `u` flag. About 28 uses across `convert`, `vault`, `stats`,
   `wrap` and `mention`: `cebabize`, mentions and anchors would quietly break on Cyrillic page names,
   and the suite has no non-ASCII text to catch it. Also `re.match` against `^` or the sticky flag,
   named groups, and `len()` against `.length` in UTF-16, which changes `wrap -w` widths.
4. **Tests.** The suite calls the CLI inside the Python process: port it or call the binary as a separate process.
5. **Sharing code with a single-file page needs a build step.** The page is plain JS with no bundler,
   sharing modules means inlining them into the HTML at build. TS makes it worse, browsers do not run `.ts`.
6. **Install changes.** Users move from `mise pipx:hiqsol/uwiki` to an npm package, name `uwiki` not checked,
   or per-platform binaries from `bun build --compile`, size not measured. The release workflow is rewritten.
7. **Performance does not justify it.** Caching `named` and `lookup` by name and source folder likely brings
   `build` near 1s in Python, not tried. The 0.14s startup does not matter for a CLI, nor at all for `lsp` and `serve`.

## How to decide

The question: will the page ever resolve links or render markdown itself, for live editing, comments
or `serve` without rebuilding?

- **No:** stay in Python, cache the lookup, add type hints checked by pyright for types.
- **Yes:** a partial port is the worst option, resolving links both in Python and JS breaks the rule
  that new features reuse the vault resolver, not a copy of it. Port everything:
  1. Finish "Page parsed once" first, its page record is the model to share with the browser.
  2. Write plain ES modules with JSDoc types and `// @ts-check`, checked by `tsc` in CI,
     the same files run in Node 24 and the browser without a build step.
  3. Use Node, which 8bitgalaxy already uses, with `smol-toml` as the one extra dependency.
  4. Keep the Python suite as the reference: run it against the JS binary,
     and diff the output of both on 8bitgalaxy until they match.
  5. Add Cyrillic fixtures before porting anything.
