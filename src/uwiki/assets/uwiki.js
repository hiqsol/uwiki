(function () {
  "use strict";

  var WORD = /[\p{L}\p{N}]+/gu;
  var WORD_SPLIT = /([\p{L}\p{N}]+)/u;
  var MAX_HITS = 30;  // sections listed under a page in the sidebar
  var URL_KEY = "q";

  var content = document.querySelector(".content");
  var sidebar = document.getElementById("sidebar");
  var lists = document.getElementById("_lists");
  var toc = document.getElementById("toc");
  var query = document.getElementById("query");
  var stats = document.getElementById("stats");
  var facets = document.getElementById("facets");
  var filters = document.getElementById("_filters");
  var fold = document.getElementById("fold");
  var counts = document.getElementById("counts");
  var problems = document.getElementById("problems");
  var pages = Array.prototype.slice.call(document.querySelectorAll(".content .page"));
  var data = readData();
  var tocLinks = {};
  var active = null;
  var sections = null;  // search index, built on first search
  var vocab = new Map();
  var termCache = new Map();
  var nodes = [];  // page headers in order with their tree, elements and state
  var nodeOf = new Map();  // page header: node
  var refs = null;  // page header: links to it and backlink titles naming it, read on first filtering
  var pageOfId = null;  // id: page header it is under
  var shownPages = pages;  // page headers in the page, for spy
  var marks = [];  // current search marks in content
  var markAt = -1;


  function readData() {
    var el = document.getElementById("data");
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return { facets: [], pages: {}, backlinks: {} };
    }
  }

  var READ_WPM = 230;  // words read a minute, for reading time

  // metadata and front matter blocks built from the data go before crumb and title, floating right one over
  // the other; metadata takes in what check reports, built into the header; their tables are built
  // when first unfolded, here or in a preview copying them, so opening the page builds folded lines only
  var issuesOf = new Map();  // page id: what check reports, taken out of its header

  function floatAsides() {
    pages.forEach(function (h) {
      var info = data.pages[h.id], problems = h.querySelector(":scope > details.problems");
      var issues = problems ? problems.querySelector(":scope > div") : null;
      if (issues && issues.children.length) issuesOf.set(h.id, issues);
      var blocks = [metadataBlock(h.id, info, data.backlinks[h.id] || [], issues)];
      if (problems) problems.remove();
      if (info && data.frontMatter !== false) blocks.push(frontMatterBlock(h.id, info));
      blocks.filter(Boolean).reverse().forEach(function (block) { h.insertBefore(block, h.firstChild); });
    });
    document.addEventListener("toggle", function (e) {
      var block = e.target;
      if (!block.open || !block.dataset || !("page" in block.dataset) || block.querySelector(":scope > table")) return;
      var id = block.dataset.page, table = block.classList.contains("metadata")
        ? metadataTable(id, data.pages[id], data.backlinks[id] || [], issuesOf.get(id))
        : frontTable(frontItems(data.pages[id]));
      block.appendChild(table);
      if (content.contains(block)) addRefs(table);
    }, true);
  }

  // metadata as folded line of problems, tokens, backlinks and file name unfolding into a table of problems
  // with links to where they are, stats, links to linking pages, file name and folder; file name and folder
  // only where title and crumb don't tell them, problems and backlinks only if any
  function metadataBlock(id, info, links, issues) {
    var line = [], b = null;
    if (issues) {
      b = document.createElement("b");
      b.className = issuesKind(issues);
      b.textContent = plural(issues.children.length, b.className);
    }
    if (info) line.push(short(info.tokens || 0) + " tokens");
    if (links.length) line.push(plural(links.length, "backlink"));
    if (info && info.file) line.push(info.file);
    if (!b && !info && !links.length) return null;
    var block = details("metadata"), span = document.createElement("span");
    block.dataset.page = id;
    if (b) span.appendChild(b);
    span.appendChild(document.createTextNode((b && line.length ? " · " : "") + line.join(" · ")));
    block.firstChild.appendChild(span);
    return block;
  }

  function issuesKind(issues) {
    return issues.querySelector("a.problem") ? "problem" : "warning";
  }

  // the unfolded metadata: problems linking to their lines, else to the page, stats, backlinks, file and folder
  function metadataTable(id, info, links, issues) {
    var rows = [];
    if (issues) {
      issues = issues.cloneNode(true);
      issues.querySelectorAll("a").forEach(function (a) {
        var to = decodeURIComponent(a.getAttribute("href").slice(1));
        if (!document.getElementById(to)) a.setAttribute("href", "#" + id);
      });
      rows.push([plural(issues.children.length, issuesKind(issues)), issues, "issues"]);
    }
    if (info) {
      var minutes = Math.max(1, Math.round((info.words || 0) / READ_WPM));
      rows.push(["Stats", [short(info.words || 0) + " words", short(info.tokens || 0) + " tokens",
                           plural(minutes, "minute")].join(" · ")]);
    }
    if (links.length) rows.push([plural(links.length, "backlink"), backlinks(links)]);
    if (info && info.file) rows.push(["Filename", info.file]);
    if (info && info.dir) rows.push(["Dir", info.dir]);
    var table = document.createElement("table");
    rows.forEach(function (row) {
      var tr = table.insertRow(), th = document.createElement("th"), td = tr.insertCell();
      th.textContent = row[0];
      tr.insertBefore(th, td);
      if (row[2]) td.className = row[2];
      if (typeof row[1] === "string") td.textContent = row[1];
      else td.appendChild(row[1]);
    });
    return table;
  }

  // links to the linking pages, to the heading a link leads to
  function backlinks(links) {
    var div = document.createElement("div");
    links.forEach(function (link, i) {
      var anchor = Array.isArray(link) ? link[0] : link, heading = Array.isArray(link) ? link[1] : "";
      var source = document.getElementById(anchor);
      var a = document.createElement("a");
      a.href = "#" + anchor;
      a.textContent = (source ? titleOf(source) : anchor) + (heading ? " › " + heading : "");
      if (i) div.appendChild(document.createTextNode(", "));
      div.appendChild(a);
    });
    return div;
  }

  function plural(n, word) {
    return n + " " + word + (n === 1 ? "" : "s");
  }

  // front matter as folded line of values unfolding into one table of keys and values:
  // a nested key beside the key above it spanning its rows, a list of maps an item after another;
  // none for title only
  function frontMatterBlock(id, info) {
    var items = frontItems(info);
    var line = Object.keys(items).filter(function (key) { return key !== "title"; }).map(function (key) {
      return frontText(items[key]);
    }).filter(Boolean).join(" · ");
    if (!line) return null;
    var block = details("front-matter" + (info.frontProblem ? " problem" : ""));
    var span = document.createElement("span");
    block.dataset.page = id;
    span.textContent = line;
    block.firstChild.appendChild(span);
    return block;
  }

  // top level front matter keys with nested maps and lists of maps as such
  function frontItems(info) {
    var items = {}, nested = info.nested || {};
    Object.keys(info.meta).forEach(function (key) { items[key] = key in nested ? nested[key] : info.meta[key]; });
    return items;
  }

  function details(className) {
    var block = document.createElement("details");
    block.className = className;
    block.appendChild(document.createElement("summary"));
    return block;
  }

  function isMap(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  // value as one line: its texts joined
  function frontText(value) {
    if (isMap(value)) value = Object.keys(value).map(function (key) { return value[key]; });
    if (Array.isArray(value)) return value.map(frontText).filter(Boolean).join(", ");
    return value === null || value === undefined ? "" : String(value);
  }

  function frontTable(items) {
    var rows = frontRows(items, []);
    var depth = Math.max.apply(null, rows.map(function (row) { return row.keys.length; }));
    var spans = new Map(), seen = new Set();
    rows.forEach(function (row) {
      row.keys.forEach(function (node) { spans.set(node.id, (spans.get(node.id) || 0) + 1); });
    });
    var table = document.createElement("table");
    rows.forEach(function (row) {
      var tr = table.insertRow();
      if (row.item) tr.className = "item";
      row.keys.forEach(function (node, level) {
        if (seen.has(node.id)) return;
        seen.add(node.id);
        var th = document.createElement("th");
        th.textContent = node.key;
        if (spans.get(node.id) > 1) th.rowSpan = spans.get(node.id);
        if (level === row.keys.length - 1 && depth - level > 1) th.colSpan = depth - level;
        tr.appendChild(th);
      });
      var td = document.createElement("td");
      td.textContent = row.text;
      tr.appendChild(td);
    });
    return table;
  }

  // rows of value as {keys, text, item: starts list item}, keys as {id: path, key} from the top one
  function frontRows(value, path) {
    var rows = [];
    if (isMap(value) && Object.keys(value).length) {
      Object.keys(value).forEach(function (key) {
        var at = path.concat([key]), node = { id: JSON.stringify(at), key: key };
        frontRows(value[key], at).forEach(function (row) {
          rows.push({ keys: [node].concat(row.keys), text: row.text, item: row.item });
        });
      });
      return rows;
    }
    if (Array.isArray(value) && value.some(isMap)) {
      value.forEach(function (v, n) {
        frontRows(isMap(v) ? v : { "": v }, path.concat([n])).forEach(function (row, i) {
          rows.push({ keys: row.keys, text: row.text, item: row.item || (n > 0 && i === 0) });
        });
      });
      return rows;
    }
    return [{ keys: [], text: frontText(value), item: false }];
  }

  // code blocks drawing boxes get line height they join at, see pre.box-drawing
  function markBoxDrawing() {
    document.querySelectorAll(".content pre").forEach(function (pre) {
      if (/[\u2500-\u259f]/.test(pre.textContent)) pre.classList.add("box-drawing");
    });
  }

  function titleOf(h) {
    return h.dataset.title || h.textContent;
  }

  // TOC

  // page headers as a tree of {h, kids} by their level
  function headerTree(headers) {
    var root = { kids: [] }, stack = [];
    Array.prototype.forEach.call(headers, function (h) {
      if (!h.id) return;
      var item = { h: h, level: +h.tagName[1], kids: [] };
      while (stack.length && stack[stack.length - 1].level >= item.level) stack.pop();
      (stack.length ? stack[stack.length - 1] : root).kids.push(item);
      stack.push(item);
    });
    return root.kids;
  }

  function tocEntry(item) {
    var a = document.createElement("a");
    a.className = "entry";
    a.href = "#" + item.h.id;
    a.textContent = a.title = titleOf(item.h);
    tocLinks[item.h.id] = a;
    return a;
  }

  // a tree of items of the sidebar, the TOC or facets: an li per item with the entry entryOf gives it,
  // a branch folded with a toggle and an ul of its kids, onFlip called when one is folded or unfolded
  function buildTree(ul, items, entryOf, onFlip) {
    items.forEach(function (item) {
      var li = document.createElement("li");
      ul.appendChild(li);
      li.appendChild(entryOf(item, li));
      if (!item.kids.length) return;
      var sub = document.createElement("ul");
      li.appendChild(sub);
      li.classList.add("collapsed");
      li.insertBefore(toggle(li, onFlip), li.firstChild);
      buildTree(sub, item.kids, entryOf, onFlip);
    });
  }

  // the button and the entry of a branch both fold and unfold it, a link entry also goes to its page,
  // a box in the entry does not fold it
  function toggle(li, onFlip) {
    var button = document.createElement("button");
    button.className = "toggle";
    button.type = "button";
    button.setAttribute("aria-label", "Toggle section");
    button.textContent = "▼";
    var flip = function (e) {
      if (e.target.closest(".check")) return;
      li.classList.toggle("collapsed");
      delete li.dataset.auto;
      onFlip(li);
    };
    button.addEventListener("click", flip);
    li.querySelector(":scope > .entry").addEventListener("click", flip);
    return button;
  }

  // one triangle for the whole tree, as a branch has: expands all when any branch is collapsed, else collapses all
  function updateFold() {
    var collapsed = !!toc.querySelector("li.collapsed");
    fold.hidden = !toc.querySelector("li > .toggle");
    fold.classList.toggle("collapsed", collapsed);
    fold.title = collapsed ? "Expand all" : "Collapse all";
    fold.setAttribute("aria-label", fold.title);
  }

  // collapses all for true, expands for false, else flips as the triangle does
  function foldAll(collapse) {
    if (typeof collapse !== "boolean") collapse = !toc.querySelector("li.collapsed");
    toc.querySelectorAll("li > .toggle").forEach(function (button) {
      var li = button.parentNode;
      li.classList.toggle("collapsed", collapse);
      delete li.dataset.auto;
    });
    updateFold();
  }

  // section of the page, its top is 16px over the page title: measuring it lays out no page far from the window
  function boxOf(h) {
    return h.parentNode.tagName === "SECTION" ? h.parentNode : h;
  }

  // size of a page not drawn yet, by its words, so the scrollbar fits the whole vault before pages are drawn
  function sizePages() {
    var width = content.clientWidth || 800;
    pages.forEach(function (h) {
      var box = boxOf(h), info = data.pages[h.id];
      if (box === h) return;
      var height = info ? 230 + 1900 * scale * scale * (1 + space / 1.6) * info.words / width : 70;
      box.style.containIntrinsicSize = "auto " + Math.round(height * (info ? 1 : scale)) + "px";
    });
  }

  // a heading or item jumped to lands below the sticky header of its page: the header is measured
  // just before the jump, measuring every page's header would lay out pages far from the window
  function clearHead(id) {
    var el = id && document.getElementById(id);
    var box = el && el.closest(".content > section");
    if (!box || el.parentNode === box && el.classList.contains("page")) return;
    var h = box.querySelector(":scope > .page");
    if (h) box.style.setProperty("--head", h.offsetHeight + "px");
  }
  // a page header sticks: above the window it sits at the end of its page, where a jump to it would land,
  // so it stops sticking till the jump is done; then it is at the top of the window, sticking moves it not
  function unstick(id) {
    var el = id && document.getElementById(id);
    if (!el || !el.classList.contains("page") || boxOf(el) === el) return;
    el.style.position = "static";
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { el.style.position = ""; });
    });
  }

  // a heading or item lands below its page header, a page where it starts
  function jumpTo(el) {
    clearHead(el.id);
    unstick(el.id);
    el.scrollIntoView();
  }

  function hashId(href) {
    try {
      return decodeURIComponent(href.slice(href.indexOf("#") + 1));
    } catch (e) {
      return "";
    }
  }

  function topOf(h) {
    var box = boxOf(h);
    return box.getBoundingClientRect().top + (box === h ? 0 : 16);
  }

  // highlights TOC entry of the page being read, unfolds its branch
  function spy() {
    var pages = shownPages;
    var lo = 0, hi = pages.length - 1, current = pages[0];
    while (lo <= hi) {
      var mid = (lo + hi) >> 1;
      if (topOf(pages[mid]) <= 80) {
        current = pages[mid];
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    var a = current && tocLinks[current.id];
    if (a === active) return;
    if (active) active.classList.remove("active");
    active = a;
    toc.querySelectorAll("li[data-auto]").forEach(function (li) {
      if (!a || !li.contains(a)) {
        li.classList.add("collapsed");
        delete li.dataset.auto;
      }
    });
    if (a) {
      for (var li = a.parentNode.parentNode.closest("li"); li && toc.contains(li); li = li.parentNode.closest("li")) {
        if (li.classList.contains("collapsed")) {
          li.classList.remove("collapsed");
          li.dataset.auto = "";
        }
      }
    }
    updateFold();
    if (!a) return;
    a.classList.add("active");
    var r = a.getBoundingClientRect(), t = lists.getBoundingClientRect(), top = t.top + stats.offsetHeight;
    if (r.top < top || r.bottom > t.bottom) {
      lists.scrollTop += r.top - top - (t.bottom - top) / 3;
    }
  }

  // search index: section is text from a heading with id till next one

  function words(text) {
    return text.toLowerCase().match(WORD) || [];
  }

  function buildIndex() {
    sections = [];
    var heads = content.querySelectorAll("h1[id], h2[id], h3[id], h4[id], h5[id], h6[id]");
    var range = document.createRange();
    var page = null;
    for (var i = 0; i < heads.length; i++) {
      var h = heads[i];
      if (h.classList.contains("page")) page = h;
      range.setStartAfter(h);
      if (i + 1 < heads.length) {
        range.setEndBefore(heads[i + 1]);
      } else {
        range.setEnd(content, content.childNodes.length);
      }
      var s = {
        head: h,
        next: heads[i + 1] || null,
        title: titleOf(h),
        page: page,
        text: textOf(range).replace(/\s+/g, " ").trim(),
        headWords: new Set(words(titleOf(h) + " " + (h.dataset.aliases || ""))),
        counts: new Map()
      };
      s.lower = s.text.toLowerCase();
      var index = sections.push(s) - 1;
      s.headWords.forEach(add);
      words(s.text).forEach(add);
    }
    function add(w) {
      var s = sections[index];
      s.counts.set(w, (s.counts.get(w) || 0) + 1);
      var list = vocab.get(w);
      if (!list) vocab.set(w, list = []);
      if (list[list.length - 1] !== index) list.push(index);
    }
  }

  // text of the range without parts added by build, as metadata
  function textOf(range) {
    var frag = range.cloneContents();
    frag.querySelectorAll(".metadata, .problems").forEach(function (el) { el.remove(); });
    return frag.textContent;
  }

  // fuzzy search: exact, prefix, substring, typos and abbreviations of every query word,
  // fuzzy ones only when the word has no exact or prefix matches

  function similarity(t, w) {
    if (w === t) return 1;
    if (w.startsWith(t)) return 0.8 + 0.1 * t.length / w.length;
    if (t.length < 3) return 0;
    if (w.includes(t)) return 0.6;
    if (t.length >= 5) {
      var max = t.length >= 8 ? 2 : 1;
      if (Math.abs(w.length - t.length) <= max) {
        var d = distance(t, w, max);
        if (d <= max) return d == 1 ? 0.55 : 0.4;
      }
      if (w.length > t.length && distance(t, w.slice(0, t.length), 1) <= 1) return 0.45;
    }
    if (t[0] == w[0] && t.length * 2 >= w.length && subsequence(t, w)) return 0.3 * t.length / w.length;
    return 0;
  }

  // edit distance with transpositions, gives up beyond max
  function distance(a, b, max) {
    var prev2 = null, prev = [], cur;
    for (var j = 0; j <= b.length; j++) prev[j] = j;
    for (var i = 1; i <= a.length; i++) {
      cur = [i];
      var low = i;
      for (j = 1; j <= b.length; j++) {
        var cost = a[i - 1] == b[j - 1] ? 0 : 1;
        cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
        if (prev2 && i > 1 && j > 1 && a[i - 1] == b[j - 2] && a[i - 2] == b[j - 1]) {
          cur[j] = Math.min(cur[j], prev2[j - 2] + 1);
        }
        low = Math.min(low, cur[j]);
      }
      if (low > max) return max + 1;
      prev2 = prev;
      prev = cur;
    }
    return prev[b.length];
  }

  function subsequence(t, w) {
    var j = 0;
    for (var i = 0; i < w.length && j < t.length; i++) {
      if (w[i] == t[j]) j++;
    }
    return j == t.length;
  }

  function matchTerm(t) {
    var res = termCache.get(t);
    if (res) return res;
    res = [];
    vocab.forEach(function (_, w) {
      var sim = similarity(t, w);
      if (sim > 0) res.push([w, sim]);
    });
    var strong = res.some(function (m) { return m[1] >= 0.8; });
    if (strong) res = res.filter(function (m) { return m[1] >= 0.8; });
    termCache.set(t, res);
    return res;
  }

  // filter: the search box shows only pages matching all its terms, in the order of the full page,
  // folders of shown pages stay by title; a word matches as search does, "text" exactly as written,
  // key:value front matter, in:folder by path or title, is:problem, - before a term negates

  var TOKEN = /(-?)(?:([^\s:"]+):(?:"([^"]*)"?|(\S*))|"([^"]*)"?|(\S+))/g;
  var SPECIAL = ["in", "is"];
  var keyNames = null;  // lowercase key: key as pages have it
  var valueSets = {};  // key: its values in the vault, lowercase
  var folderPaths = null, folderTitles = null;
  var marking = null, saving = null;

  function readNodes() {
    var stack = [];
    pages.forEach(function (h) {
      var level = +h.tagName[1];
      while (stack.length && stack[stack.length - 1].level >= level) stack.pop();
      var a = tocLinks[h.id];
      var node = {
        h: h, level: level, parent: stack[stack.length - 1] || null, info: data.pages[h.id] || null,
        title: titleOf(h).toLowerCase(), els: [], li: a ? a.parentNode : null, link: a || null,
        isFolder: false, state: "shown", next: "shown"
      };
      if (node.parent) node.parent.isFolder = true;
      for (var n = h.nextElementSibling; n && !n.classList.contains("page"); n = n.nextElementSibling) node.els.push(n);
      nodes.push(node);
      nodeOf.set(h, node);
      stack.push(node);
    });
  }

  // share of tokens of a page with the pages under it right of its sidebar entry, always on a branch
  // and on a leaf over 5%, on hover on other leaves, tokens beside it on hover; bars from the right edge as dust draws them: the share
  // of an entry over the lighter one of its branch
  function showSizes() {
    nodes.forEach(function (n) {
      if (!n.link) return;
      n.size = sizeOf("tokens");
      if (!n.isFolder) n.size.classList.add("leaf");
      n.link.insertBefore(n.size, n.link.firstChild);
    });
    var all = sizeBy(nodes.filter(function (n) { return !!n.info; }));
    nodes.forEach(function (n) {
      if (n.link && n.tokens) n.link.title += "\n" + n.tokens.toLocaleString("en") + " tokens"
        + (n.count > 1 ? " in " + n.count + " pages" : "") + ", " + percent(100 * n.tokens / all) + " of all";
    });
  }

  // shares of the tokens of the given pages: of all, or of those found when filtering
  function sizeBy(matched) {
    var all = 0;
    nodes.forEach(function (n) { n.tokens = 0; n.count = 0; });
    matched.forEach(function (n) {
      var tokens = n.info.tokens || 0;
      all += tokens;
      for (var p = n; p; p = p.parent) {
        p.tokens += tokens;
        p.count++;
      }
    });
    nodes.forEach(function (n) {
      if (!n.size) return;
      n.size.hidden = !n.tokens;
      setSize(n.link, n.size, all ? 100 * n.tokens / all : 0,
              n.parent && n.parent.link && all ? 100 * n.parent.tokens / all : null, short(n.tokens) + " · ");
    });
    return all;
  }

  // size of a tree entry: a span of the text named cls, then the share
  function sizeOf(cls) {
    var size = document.createElement("span");
    size.className = "size";
    [cls, "share"].forEach(function (name) {
      var el = document.createElement("span");
      el.className = name;
      size.appendChild(el);
    });
    return size;
  }

  // share of a tree entry, as a bar too over the lighter one of its branch share when given
  function setSize(entry, size, share, branch, text) {
    size.classList.toggle("big", share > 5);
    size.firstChild.textContent = text;
    size.lastChild.textContent = percent(share);
    entry.style.setProperty("--share", share.toFixed(2));
    if (branch === null) entry.style.removeProperty("--branch");
    else entry.style.setProperty("--branch", branch.toFixed(2));
  }

  function percent(p) {
    return (p >= 10 ? Math.round(p) : p >= 0.1 ? p.toFixed(1).replace(/\.0$/, "") : "<0.1") + "%";
  }

  // links to pages, greyed when their page is filtered out: read when filtering first hides a page,
  // links of a metadata table unfolded later are added then
  function refsOf(h) {
    if (!refs) {
      refs = new Map();
      pageOfId = new Map();
      var cur = null;
      content.querySelectorAll("[id]").forEach(function (el) {
        if (el.classList.contains("page")) cur = el;
        pageOfId.set(el.id, cur);
      });
      addRefs(content);
    }
    return refs.get(h) || [];
  }

  function addRefs(root) {
    if (!refs) return;
    root.querySelectorAll("a[href^='#']").forEach(function (a) {
      var page = !a.classList.contains("item-anchor") && pageOfId.get(decodeURIComponent(a.getAttribute("href").slice(1)));
      if (!page) return;
      if (!refs.has(page)) refs.set(page, []);
      refs.get(page).push(a);
      a.classList.toggle("off", nodeOf.get(page).state === "hidden");
    });
  }

  function keyOf(name) {
    if (!keyNames) {
      keyNames = new Map();
      SPECIAL.forEach(function (k) { keyNames.set(k, k); });
      data.facets.forEach(function (f) { keyNames.set(f[0].toLowerCase(), f[0]); });
      nodes.forEach(function (n) {
        if (n.info) Object.keys(n.info.meta).forEach(function (k) { keyNames.set(k.toLowerCase(), k); });
      });
    }
    return keyNames.get(name.toLowerCase()) || null;
  }

  // terms of the box: {kind: key, key, value} | {kind: word, w} | {kind: phrase, text}, with neg, at and raw
  function parse(q) {
    var terms = [], m;
    TOKEN.lastIndex = 0;
    while ((m = TOKEN.exec(q))) {
      var term = { neg: m[1] === "-", at: m.index, raw: m[0] };
      if (m[2] !== undefined) {
        var key = keyOf(m[2]), value = m[3] !== undefined ? m[3] : m[4];
        if (key) {
          if (value) terms.push(Object.assign(term, { kind: "key", key: key, value: value.toLowerCase() }));
          continue;  // key being typed, no value yet
        }
        pushWords(terms, term, m[2] + " " + value);
      } else if (m[5] !== undefined) {
        if (m[5]) terms.push(Object.assign(term, { kind: "phrase", text: m[5] }));
      } else {
        pushWords(terms, term, m[6]);
      }
    }
    return terms;
  }

  function pushWords(terms, term, text) {
    words(text).forEach(function (w) { terms.push(Object.assign({}, term, { kind: "word", w: w })); });
  }

  function valuesOf(node, key) {
    var v = node.info.meta[key];
    if (v === undefined || v === null || v === "") return [];
    return (Array.isArray(v) ? v : [v]).map(function (x) { return String(x).toLowerCase(); });
  }

  function valueSet(key) {
    if (!valueSets[key]) {
      var set = valueSets[key] = new Set();
      nodes.forEach(function (n) { if (n.info) valuesOf(n, key).forEach(function (v) { set.add(v); }); });
    }
    return valueSets[key];
  }

  // value matches exactly when the vault has it or values nested under it, as tech for tech/action,
  // these too then; else by prefix, so a value being typed already filters; * matches any value
  function matcher(t) {
    if (t.key === "in") return folderMatcher(t.value.replace(/\/+$/, ""));
    if (t.key === "is") return problemMatcher(t.value);
    if (t.value === "*") return function (node) { return valuesOf(node, t.key).length > 0; };
    var set = valueSet(t.key), exact = set.has(t.value);
    if (!exact) set.forEach(function (v) { if (v.startsWith(t.value + "/")) exact = true; });
    return function (node) {
      return valuesOf(node, t.key).some(function (v) { return exact ? isUnder(v, t.value) : v.startsWith(t.value); });
    };
  }

  // whether value v is value or nested under it
  function isUnder(v, value) {
    return v === value || v.startsWith(value + "/");
  }

  function folderMatcher(f) {
    if (!folderPaths) {
      folderPaths = new Set();
      folderTitles = new Set();
      nodes.forEach(function (n) {
        if (n.isFolder) folderTitles.add(n.title);
        if (!n.info) return;
        var parts = n.info.path.toLowerCase().split("/");
        for (var i = 1; i < parts.length; i++) folderPaths.add(parts.slice(0, i).join("/"));
      });
    }
    var exact = folderPaths.has(f) || folderTitles.has(f);
    var like = function (s) { return exact ? s === f : s.startsWith(f); };
    return function (node) {
      var path = node.info.path.toLowerCase();
      var dir = path.slice(0, Math.max(0, path.lastIndexOf("/")));
      if (dir && (exact ? (dir + "/").startsWith(f + "/") : dir.startsWith(f))) return true;
      for (var n = node; n; n = n.parent) {
        if ((n !== node || n.isFolder) && like(n.title)) return true;
      }
      return false;
    };
  }

  function problemMatcher(value) {
    var hit = "problem".startsWith(value) || "problems".startsWith(value);
    return function (node) { return hit && node.info.problems > 0; };
  }

  // section index: count of words or phrase in it
  function textHits(t) {
    if (!sections) buildIndex();
    var res = new Map();
    if (t.kind === "word") {
      t.matches = matchTerm(t.w).map(function (m) { return m[0]; });
      t.matches.forEach(function (w) {
        vocab.get(w).forEach(function (si) { res.set(si, (res.get(si) || 0) + sections[si].counts.get(w)); });
      });
    } else {
      sections.forEach(function (s, si) {
        var n = count(s.text, t.text) + count(s.title, t.text);
        if (n) res.set(si, n);
      });
    }
    return res;
  }

  function count(text, part) {
    var n = 0;
    for (var i = text.indexOf(part); i >= 0; i = text.indexOf(part, i + part.length)) n++;
    return n;
  }

  // terms with what they match: groups of key terms by key, text terms with their sections and pages
  function prepare(terms) {
    var groups = new Map(), texts = [];
    terms.forEach(function (t) {
      if (t.kind === "key") {
        var g = groups.get(t.key);
        if (!g) groups.set(t.key, g = { pos: [], neg: [] });
        (t.neg ? g.neg : g.pos).push(matcher(t));
      } else {
        t.hits = textHits(t);
        t.pages = new Set();
        t.hits.forEach(function (_, si) { t.pages.add(sections[si].page); });
        texts.push(t);
      }
    });
    return { terms: terms, groups: groups, texts: texts };
  }

  // built pages matching all terms, key terms of skipped key left out
  function match(prep, skip) {
    return nodes.filter(function (node) {
      if (!node.info) return false;
      var ok = true;
      prep.groups.forEach(function (g, key) {
        if (!ok || key === skip) return;
        if (g.pos.length && !g.pos.some(function (f) { return f(node); })) ok = false;
        else if (g.neg.some(function (f) { return f(node); })) ok = false;
      });
      return ok && prep.texts.every(function (t) { return t.pages.has(node.h) !== t.neg; });
    });
  }

  function update() {
    var q = query.value;
    var prep = prepare(parse(q));
    var filtering = prep.terms.length > 0;
    var matched = filtering ? match(prep, null) : nodes.filter(function (n) { return !!n.info; });
    setStates(matched, filtering);
    sizeBy(matched);
    showHits(prep, matched);
    showStats(matched, filtering);
    showFacets(prep, matched, filtering);
    clearTimeout(marking);
    marking = setTimeout(function () { marking = null; markHits(prep); }, 120);
    clearTimeout(saving);
    saving = setTimeout(function () { saveQuery(q); }, 300);
  }

  // shown: page with its text, context: folder of a shown page by title only, hidden
  function setStates(matched, filtering) {
    nodes.forEach(function (n) { n.next = filtering ? "hidden" : "shown"; });
    matched.forEach(function (n) {
      n.next = "shown";
      for (var p = n.parent; p && p.next === "hidden"; p = p.parent) p.next = "context";
    });
    nodes.forEach(function (n) {
      if (n.next === n.state) return;
      if ((n.next === "hidden") !== (n.state === "hidden")) {
        refsOf(n.h).forEach(function (el) { el.classList.toggle("off", n.next === "hidden"); });
      }
      n.state = n.next;
      n.h.hidden = n.state === "hidden";
      if (boxOf(n.h) !== n.h) {
        boxOf(n.h).hidden = n.state === "hidden";
        boxOf(n.h).classList.toggle("context", n.state === "context");
      }
      n.h.classList.toggle("context", n.state === "context");
      n.els.forEach(function (el) { el.hidden = n.state !== "shown"; });
      if (n.li) {
        n.li.hidden = n.state === "hidden";
        n.li.classList.toggle("context", n.state === "context");
      }
    });
    toc.classList.toggle("filtering", filtering);
    content.classList.toggle("filtering", filtering);
    toc.classList.toggle("none", filtering && !matched.length);
    shownPages = pages.filter(function (h) { return nodeOf.get(h).state !== "hidden"; });
    active = null;
    toc.querySelectorAll("a.active").forEach(function (a) { a.classList.remove("active"); });
    updateFold();
    spy();
  }

  // sections of shown pages having the words, listed under their page in the sidebar with counts
  function showHits(prep, matched) {
    toc.querySelectorAll(".hits, .count").forEach(function (el) { el.remove(); });
    var counts = sectionCounts(prep);
    if (!counts.size) return;
    var bySection = new Map();
    counts.forEach(function (n, si) {
      var node = nodeOf.get(sections[si].page);
      if (node.state !== "shown") return;
      if (!bySection.has(node)) bySection.set(node, []);
      bySection.get(node).push(si);
    });
    var budget = 400;
    matched.forEach(function (node) {
      var list = bySection.get(node);
      if (!list || !node.link) return;
      node.link.appendChild(countOf(list.reduce(function (a, si) { return a + counts.get(si); }, 0)));
      var ul = document.createElement("ul");
      ul.className = "hits";
      list.sort(function (a, b) { return a - b; }).forEach(function (si) {
        var s = sections[si];
        if (s.head === node.h || budget <= 0 || ul.children.length >= MAX_HITS) return;
        budget--;
        var li = document.createElement("li");
        var a = document.createElement("a");
        a.className = "entry";
        a.href = "#" + s.head.id;
        a.textContent = a.title = s.title;
        a.appendChild(countOf(counts.get(si)));
        li.appendChild(a);
        ul.appendChild(li);
      });
      if (ul.children.length) node.link.after(ul);
    });
  }

  function sectionCounts(prep) {
    var counts = new Map();
    prep.texts.forEach(function (t) {
      if (t.neg) return;
      t.hits.forEach(function (n, si) { counts.set(si, (counts.get(si) || 0) + n); });
    });
    return counts;
  }

  function countOf(n) {
    var el = document.createElement("span");
    el.className = "count";
    el.textContent = n;
    return el;
  }

  function showStats(matched, filtering) {
    var all = nodes.filter(function (n) { return !!n.info; });
    var sum = function (list, key) { return list.reduce(function (a, n) { return a + (n.info[key] || 0); }, 0); };
    var cols = [["pages", matched.length, all.length], ["words", sum(matched, "words"), sum(all, "words")],
                ["tokens", sum(matched, "tokens"), sum(all, "tokens")]];
    var n = sum(matched, "problems");
    counts.textContent = cols.map(function (c) {
      return (filtering ? short(c[1]) + "/" : "") + short(c[2]) + " " + c[0];
    }).join(" · ") + (n ? " · " : "");
    counts.title = cols.map(function (c) { return (filtering ? c[1] + " of " : "") + c[2] + " " + c[0]; }).join(", ");
    problems.hidden = !n;
    problems.textContent = plural(n, "problem");
    var on = parse(query.value).some(isProblemTerm);
    problems.classList.toggle("on", on);
    problems.title = on ? "Show all pages" : "Show only pages with problems";
  }

  function isProblemTerm(t) {
    return t.kind === "key" && t.key === "is" && !t.neg && "problems".startsWith(t.value);
  }

  function short(n) {
    if (n < 1000) return String(n);
    if (n < 10000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
    return Math.round(n / 1000) + "k";
  }

  // facets: a tree as the sidebar one, a branch for every schema key listing values, an entry per value,
  // values nested with slashes, as tech/action, under their group; an entry has the number and the share
  // of tokens of the pages it finds with the other terms of the box, a box adds it to them or with Shift
  // or right click takes it out, the box of a key the pages having it, key:*; the box of a value under
  // a key or group added or taken out shows it so dimmed; a folded key tells its terms of values;
  // their band counts pages with front matter and with each key, folded it tells their terms

  var OPEN_KEY = "uwiki-open-facets";
  var FOLDED_FILTERS_KEY = "uwiki-folded-filters";
  // {key, path: lowercase value or "" for the key, value: path or * for the key, li, box, size, terms, parent}
  var facetEntries = [];

  function buildFacets() {
    var open = [];
    try {
      open = JSON.parse(localStorage.getItem(OPEN_KEY) || "[]");
    } catch (e) {}
    var items = data.facets.map(function (f) { return { key: f[0], path: "", name: f[0], kids: valueTree(f[1]) }; });
    var withKey = function (items, key) {
      items.forEach(function (item) { item.key = key; withKey(item.kids, key); });
    };
    items.forEach(function (item) { withKey(item.kids, item.key); });
    var entryOf = function (item, li) {
      var parent = facetEntries.find(function (f) { return f.li === li.parentNode.parentNode; }) || null;
      var path = item.path.toLowerCase();
      var e = { key: item.key, path: path, value: path || "*", li: li, parent: parent, size: sizeOf("pages") };
      var div = document.createElement("div");
      div.className = "entry";
      div.appendChild(e.size);
      e.box = document.createElement("button");
      e.box.type = "button";
      e.box.className = "check";
      div.appendChild(e.box);
      div.appendChild(document.createTextNode(item.name));
      if (!item.path) {
        e.terms = document.createElement("span");
        e.terms.className = "terms";
        div.appendChild(e.terms);
      }
      li.dataset.id = item.key + ":" + item.path;
      facetEntries.push(e);
      return div;
    };
    buildTree(facets, items, entryOf, saveOpen);
    facets.querySelectorAll("li.collapsed").forEach(function (li) {
      if (open.indexOf(li.dataset.id) >= 0) li.classList.remove("collapsed");
    });
    facets.hidden = filters.hidden = !data.facets.length;
    var folded = false;
    try {
      folded = localStorage.getItem(FOLDED_FILTERS_KEY) === "1";
    } catch (e) {}
    foldFilters(folded);
    filters.addEventListener("click", function () {
      foldFilters(!facets.classList.contains("folded"));
      try {
        localStorage.setItem(FOLDED_FILTERS_KEY, facets.classList.contains("folded") ? "1" : "0");
      } catch (e) {}
    });
    facets.addEventListener("click", function (ev) {
      var e = facetOf(ev.target);
      if (!e || !ev.target.closest(".check") && e.li.querySelector(":scope > ul")) return;
      pick(e, ev.shiftKey);
    });
    facets.addEventListener("contextmenu", function (ev) {
      var e = facetOf(ev.target);
      if (!e) return;
      ev.preventDefault();
      pick(e, true);
    });
  }

  // facets folded into their band or unfolded
  function foldFilters(folded) {
    var button = filters.querySelector(".fold");
    facets.classList.toggle("folded", folded);
    filters.classList.toggle("folded", folded);
    button.classList.toggle("collapsed", folded);
    filters.title = button.title = folded ? "Unfold filters" : "Fold filters";
    button.setAttribute("aria-label", button.title);
  }

  function facetOf(el) {
    var entry = el.closest("#facets .entry");
    return entry && facetEntries.find(function (f) { return f.li === entry.parentNode; });
  }

  function saveOpen() {
    var ids = Array.prototype.map.call(facets.querySelectorAll("li:not(.collapsed) > .toggle"),
      function (button) { return button.parentNode.dataset.id; });
    try {
      localStorage.setItem(OPEN_KEY, JSON.stringify(ids));
    } catch (e) {}
  }

  // values as a tree of {path, name, kids} split at slashes, in order of first value under each
  function valueTree(values) {
    var root = { kids: [], at: {} };
    values.forEach(function (value) {
      var node = root, path = "";
      value.split("/").forEach(function (name) {
        path = path ? path + "/" + name : name;
        if (!node.at[name]) node.kids.push(node.at[name] = { path: path, name: name, kids: [], at: {} });
        node = node.at[name];
      });
    });
    return root.kids;
  }

  // terms of the key in the box: value or *: "+" or "-"
  function termsOf(prep, key) {
    var res = new Map();
    prep.terms.forEach(function (t) {
      if (t.kind === "key" && t.key === key) res.set(t.value, t.neg ? "-" : "+");
    });
    return res;
  }

  // whether value v of a term is under the entry: a value under its group, any value under its key
  function isBelow(e, v) {
    return e.path ? v.startsWith(e.path + "/") : v !== "*";
  }

  // state of an entry: its own term, else one of a group or key over it, implied
  function stateOf(e, terms) {
    if (terms.has(e.value)) return { sign: terms.get(e.value), implied: false };
    for (var p = e.parent; p; p = p.parent) {
      if (terms.has(p.value)) return { sign: terms.get(p.value), implied: true };
    }
    return { sign: "", implied: false };
  }

  // a click adds the entry, or drops it when added, under an added group or key takes it out instead;
  // out takes it out, or drops it when out; adding drops values under it added, taking out all under it;
  // under a group or key taken out nothing changes
  function pick(e, out) {
    var prep = prepare(parse(query.value)), state = stateOf(e, termsOf(prep, e.key));
    if (state.sign === "-" && state.implied) return;
    var mine = function (t) { return t.kind === "key" && t.key === e.key; };
    var sign = out ? "-" : "+";
    if (state.sign === sign && !state.implied) {
      editTerms(function (t) { return mine(t) && t.value === e.value; });
    } else if (state.sign === "+" && state.implied) {
      editTerms(function () { return false; }, termOf(e.key, e.value, true));
    } else {
      editTerms(function (t) {
        return mine(t) && (t.value === e.value || isBelow(e, t.value) && (out || !t.neg));
      }, termOf(e.key, e.value, out));
    }
  }

  function showFacets(prep, matched, filtering) {
    var keys = new Map(), told = [];
    facetEntries.forEach(function (e) {
      var k = keys.get(e.key);
      if (!k) {
        var others = match(prep, e.key);
        keys.set(e.key, k = {
          others: others, terms: termsOf(prep, e.key),
          tokens: others.reduce(function (a, n) { return a + (n.info.tokens || 0); }, 0)
        });
      }
      var n = 0, tokens = 0;
      k.others.forEach(function (node) {
        var values = valuesOf(node, e.key);
        if (e.path ? values.some(function (v) { return isUnder(v, e.path); }) : values.length) {
          n++;
          tokens += node.info.tokens || 0;
        }
      });
      e.share = k.tokens ? 100 * tokens / k.tokens : 0;
      var entry = e.size.parentNode;
      // a key is no entry of a tree of pages: no bar of its own nor as branch of its values
      setSize(entry, e.size, e.share, e.parent && e.parent.path ? e.parent.share : null, n + (tokens ? " · " : ""));
      if (!e.path) entry.style.removeProperty("--share");
      if (!tokens) e.size.lastChild.textContent = "";
      entry.title = e.key + ":" + e.value + "\n" + plural(n, "page") + ", "
        + tokens.toLocaleString("en") + " tokens, " + percent(e.share) + " of tokens";
      entry.classList.toggle("zero", !n);
      var state = stateOf(e, k.terms), sign = state.sign;
      var partial = !sign && Array.from(k.terms.keys()).some(function (v) { return isBelow(e, v); });
      e.box.textContent = sign === "+" ? "+" : sign === "-" ? "−" : "";
      e.box.className = "check" + (sign === "+" ? " on" : sign === "-" ? " out" : partial ? " partial" : "")
        + (state.implied ? " implied" : "");
      e.box.title = state.implied ? (sign === "+" ? "In with its group, click to take it out" : "Out with its group")
        : sign === "+" ? "Drop it, Shift click to take it out" : sign === "-" ? "Drop it, click to add it"
        : "Add it, Shift click to take it out";
      e.box.setAttribute("aria-label", e.key + ":" + e.value + " " + (sign === "+" ? "in" : sign === "-" ? "out" : "any"));
      if (!e.path) {
        var signOf = function (t) { return t[1] === "-" ? "−" : "+"; };
        var values = Array.from(k.terms).filter(function (t) { return t[0] !== "*"; });
        e.terms.textContent = values.map(function (t) { return signOf(t) + t[0]; }).join(" ");
        if (k.terms.has("*")) told.push(signOf(["*", k.terms.get("*")]) + e.key);
        if (values.length) told.push(e.key + " " + e.terms.textContent);
      }
    });
    filters.querySelector(".stats").textContent = facetStats(matched, filtering);
    filters.lastChild.textContent = told.join(" · ");
  }

  // pages with front matter and with each key, found of all when filtering
  function facetStats(matched, filtering) {
    var all = nodes.filter(function (n) { return !!n.info; });
    var count = function (pages, key) {
      return pages.filter(function (n) {
        return key ? valuesOf(n, key).length > 0 : Object.keys(n.info.meta).length > 0;
      }).length;
    };
    var of = function (key) {
      return (filtering ? short(count(matched, key)) + "/" : "") + short(count(all, key));
    };
    return of(null) + " frontmatters: " + data.facets.map(function (f) { return of(f[0]) + " " + f[0]; }).join(" · ");
  }

  function termOf(key, value, neg) {
    return (neg ? "-" : "") + key + ":" + (/[\s"]/.test(value) ? '"' + value + '"' : value);
  }

  // drops terms of the box that drop takes, then adds term when given
  function editTerms(drop, term) {
    var q = query.value;
    parse(q).filter(drop).reverse().forEach(function (t) { q = q.slice(0, t.at) + q.slice(t.at + t.raw.length); });
    q = q.replace(/\s+/g, " ").trim();
    if (term) q = (q + " " + term).trim();
    query.value = q;
    update();
  }

  // adds key:value to the box, or removes it when there, or terms same as it when given
  function toggleTerm(key, value, same) {
    var found = same || function (t) {
      return t.kind === "key" && t.key === key && !t.neg && t.value === value.toLowerCase();
    };
    if (parse(query.value).some(found)) editTerms(found);
    else editTerms(function () { return false; }, termOf(key, value, false));
  }

  // marks of words and phrases in text of shown pages, Enter and Shift+Enter go through them

  function markHits(prep) {
    clearMarks();
    marks = [];
    markAt = -1;
    var counts = sectionCounts(prep);
    if (!counts.size) return;
    var hitWords = new Set(), phrases = [];
    prep.texts.forEach(function (t) {
      if (t.neg) return;
      if (t.kind === "word") t.matches.forEach(function (w) { hitWords.add(w); });
      else phrases.push(t.text);
    });
    var range = document.createRange();
    counts.forEach(function (_, si) {
      var s = sections[si];
      if (nodeOf.get(s.page).state !== "shown") return;
      range.setStartBefore(s.head);
      if (s.next) range.setEndBefore(s.next);
      else range.setEnd(content, content.childNodes.length);
      var texts = [];
      var walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT);
      walker.currentNode = s.head;
      while (walker.nextNode() && range.intersectsNode(walker.currentNode)) {
        var parent = walker.currentNode.parentNode;
        if (!parent.closest(".metadata, .problems, .front-matter, .crumb, .item-anchor, .mermaid")) {
          texts.push(walker.currentNode);
        }
      }
      texts.forEach(function (node) {
        var frag = markUp(node.data, hitWords, phrases);
        if (frag) node.parentNode.replaceChild(frag, node);
      });
    });
    marks = Array.prototype.slice.call(content.querySelectorAll("mark.hit"));
  }

  // text with words of the set and phrases wrapped in <mark>, null when there are none
  function markUp(text, hitWords, phrases) {
    var spans = [];
    phrases.forEach(function (p) {
      for (var i = text.indexOf(p); i >= 0; i = text.indexOf(p, i + p.length)) spans.push([i, i + p.length]);
    });
    var pos = 0;
    text.split(WORD_SPLIT).forEach(function (part, i) {
      if (i % 2 && hitWords.has(part.toLowerCase())) spans.push([pos, pos + part.length]);
      pos += part.length;
    });
    if (!spans.length) return null;
    spans.sort(function (a, b) { return a[0] - b[0] || b[1] - a[1]; });
    var frag = document.createDocumentFragment(), at = 0;
    spans.forEach(function (span) {
      if (span[0] < at) return;
      if (span[0] > at) frag.appendChild(document.createTextNode(text.slice(at, span[0])));
      var mark = document.createElement("mark");
      mark.className = "hit";
      mark.textContent = text.slice(span[0], span[1]);
      frag.appendChild(mark);
      at = span[1];
    });
    if (at < text.length) frag.appendChild(document.createTextNode(text.slice(at)));
    return frag;
  }

  function clearMarks() {
    content.querySelectorAll("mark.hit").forEach(function (mark) {
      var parent = mark.parentNode;
      parent.replaceChild(document.createTextNode(mark.textContent), mark);
      parent.normalize();
    });
    renderMarked();
  }

  // next or previous mark from the last one gone to, else from the top of the window;
  // without marks next or previous shown page
  function step(dir) {
    if (marking) {
      clearTimeout(marking);
      marking = null;
      markHits(prepare(parse(query.value)));
    }
    var list = marks.length ? marks : shownPages;
    if (!list.length) return;
    var cur = marks.length && markAt >= 0 ? markAt : -1;
    if (cur >= 0) {
      cur = (cur + dir + list.length) % list.length;
    } else {
      cur = dir > 0 ? list.length - 1 : 0;
      for (var i = 0; i < list.length; i++) {
        var top = marks.length ? list[i].getBoundingClientRect().top : topOf(list[i]);
        if (dir > 0 && top > 90) { cur = i; break; }
        if (dir < 0 && top < 0) cur = i;
      }
    }
    if (marks.length) {
      if (markAt >= 0) marks[markAt].classList.remove("current");
      markAt = cur;
      marks[cur].classList.add("current");
      var details = marks[cur].closest("details");
      if (details) details.open = true;
      marks[cur].scrollIntoView({ block: "center" });
    } else {
      list[cur].scrollIntoView({ block: "start" });
    }
  }

  // Escape drops words and phrases first, key terms next
  function escape() {
    var q = query.value;
    var terms = parse(q);
    if (terms.some(function (t) { return t.kind !== "key"; })) {
      query.value = terms.filter(function (t) { return t.kind === "key"; }).map(function (t) { return t.raw; }).join(" ");
    } else if (q) {
      query.value = "";
    } else {
      query.blur();
      document.body.classList.remove("nav-open");
      return;
    }
    update();
  }

  // the box is in the URL, ?q=, so a link or reload shows the same pages
  function saveQuery(q) {
    try {
      var url = new URL(location.href);
      if (q.trim()) url.searchParams.set(URL_KEY, q.trim());
      else url.searchParams.delete(URL_KEY);
      if (url.href !== location.href) history.replaceState(history.state, "", url.href);
    } catch (e) {}
  }

  function restoreQuery() {
    var q = null;
    try {
      q = new URL(location.href).searchParams.get(URL_KEY);
    } catch (e) {}
    if (q) query.value = q;
    update();
    if (q && location.hash) {
      var target = document.getElementById(hashId(location.hash));
      if (target) jumpTo(target);
    }
  }

  // hover preview: a vault link shows its page or section in a popover, cloned from this page,
  // links in it preview too, up to MAX_PREVIEWS deep; mouse only, touch taps follow links

  var PREVIEW_DELAY = 350;
  var CLOSE_DELAY = 300;
  var MAX_PREVIEWS = 3;
  var previews = [];
  var openTimer = null;

  function bindPreviews() {
    document.addEventListener("pointerover", function (e) {
      if (e.pointerType !== "mouse") return;
      var a = previewLink(e.target);
      if (!a || a.contains(e.relatedTarget)) return;
      var level = levelOf(a);
      clearTimeout(openTimer);
      if (level >= MAX_PREVIEWS || (previews[level] && previews[level].link === a)) {
        if (previews[level]) cancelClose(level);
        return;
      }
      openTimer = setTimeout(function () { openPreview(a, level); }, PREVIEW_DELAY);
    });
    document.addEventListener("pointerout", function (e) {
      if (e.pointerType !== "mouse") return;
      var a = previewLink(e.target);
      if (!a || a.contains(e.relatedTarget)) return;
      clearTimeout(openTimer);
      var level = levelOf(a);
      if (previews[level] && previews[level].link === a) scheduleClose(level);
    });
    document.addEventListener("click", function (e) {
      // after the click, so a link in a popover is still there to follow
      if (previews.length && (!e.target.closest(".preview") || e.target.closest("a"))) {
        setTimeout(function () { closePreviews(0); });
      }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key == "Escape" && previews.length) closePreviews(0);
    });
  }

  function previewLink(el) {
    var a = el.closest && el.closest("a[href^='#']");
    if (!a || !a.closest("main.content, .preview, #sidebar") || a.closest(".preview-title")) return null;
    var target = document.getElementById(decodeURIComponent(a.getAttribute("href").slice(1)));
    if (target && !/^H[1-6]$/.test(target.tagName)) target = target.closest("li");
    return target && content.contains(target) && !a.classList.contains("item-anchor") ? a : null;
  }

  // popover the link is in, 0 for links in the page
  function levelOf(a) {
    var box = a.closest(".preview");
    for (var i = 0; i < previews.length; i++) {
      if (previews[i].el === box) return i + 1;
    }
    return 0;
  }

  function openPreview(a, level) {
    closePreviews(level);
    var target = document.getElementById(decodeURIComponent(a.getAttribute("href").slice(1)));
    var el = document.createElement("div");
    el.className = "preview";
    var title = document.createElement("a");
    title.className = "preview-title";
    title.href = a.getAttribute("href");
    title.textContent = previewTitle(target);
    var crumb = crumbOf(target.classList.contains("page") ? target : pageOf(target));
    if (crumb) {
      var span = document.createElement("span");
      span.className = "preview-crumb";
      span.textContent = crumb;
      title.insertBefore(span, title.firstChild);
    }
    // a page's metadata and front matter, folded, float right of its title as in its header
    var head = document.createElement("div");
    head.className = "content preview-head";
    asidesOf(target).forEach(function (node) {
      var copy = node.cloneNode(true);
      copy.open = false;
      head.appendChild(copy);
    });
    head.appendChild(title);
    el.appendChild(head);
    var body = document.createElement("div");
    body.className = "content preview-body";
    sectionOf(target).forEach(function (node) {
      var copy = node.cloneNode(true);
      copy.removeAttribute("id");
      copy.hidden = false;
      // a diagram's styles and arrows refer to ids in its svg
      copy.querySelectorAll("[id]:not(svg, svg *)").forEach(function (n) { n.removeAttribute("id"); });
      body.appendChild(copy);
    });
    codeBlocks(body).forEach(renderCode);
    el.appendChild(body);
    document.body.appendChild(el);
    if (el.scrollHeight > el.clientHeight + 1) el.classList.add("long");
    place(el, a);
    // unfolding metadata or front matter makes it longer
    el.addEventListener("toggle", function () {
      el.classList.toggle("long", el.scrollHeight > el.clientHeight + 1);
    }, true);
    var p = { el: el, link: a, timer: null };
    previews[level] = p;
    el.addEventListener("pointerenter", function () { cancelClose(previews.indexOf(p)); });
    el.addEventListener("pointerleave", function (e) {
      if (e.pointerType === "mouse") scheduleClose(previews.indexOf(p));
    });
  }

  // metadata and front matter of a page
  function asidesOf(target) {
    if (!target.classList.contains("page")) return [];
    return Array.prototype.slice.call(target.querySelectorAll(":scope > .metadata, :scope > .front-matter"));
  }

  // page: its text till next page; section: till next heading of same or higher level
  function sectionOf(target) {
    if (target.tagName === "A") return [target.closest("li")];
    var nodes = [];
    var page = target.classList.contains("page");
    var level = +target.tagName[1];
    for (var n = target.nextElementSibling; n; n = n.nextElementSibling) {
      if (n.classList.contains("page")) break;
      if (!page && /^H[1-6]$/.test(n.tagName) && +n.tagName[1] <= level) break;
      if (!n.classList.contains("metadata") && !n.classList.contains("problems")) nodes.push(n);
    }
    return nodes;
  }

  function previewTitle(target) {
    if (target.classList.contains("page")) return titleOf(target);
    if (target.tagName === "A") {
      var li = target.closest("li"), item = li.querySelector(".item-anchor"), page = pageOf(li);
      return (page ? titleOf(page) + " › " : "") + (item ? item.dataset.item : "");
    }
    var page = pageOf(target);
    return (page ? titleOf(page) + " › " : "") + target.textContent;
  }

  // folders of the page as its header shows them, so a preview tells where the link leads
  function crumbOf(page) {
    var crumb = page && page.querySelector(":scope > .crumb");
    return crumb ? crumb.textContent : "";
  }

  function pageOf(el) {
    var page = null;
    for (var i = 0; i < pages.length && pages[i].compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING; i++) {
      page = pages[i];
    }
    return page;
  }

  // under the link, above it when there is no room below, inside the window;
  // a sidebar link's beside the sidebar, so the entries around the link stay in sight
  function place(el, a) {
    var r = a.getClientRects()[0] || a.getBoundingClientRect();
    var h = el.offsetHeight, w = el.offsetWidth;
    var width = document.documentElement.clientWidth;
    var side = a.closest("#sidebar") ? sidebar.getBoundingClientRect().right + 8 : -1;
    var top, left;
    if (side >= 0 && side + w <= width - 8) {
      top = Math.max(8, Math.min(r.top - 10, window.innerHeight - h - 8));
      left = side;
    } else {
      top = r.bottom + 6;
      if (top + h > window.innerHeight && r.top - h - 6 > 0) top = r.top - h - 6;
      left = Math.max(8, Math.min(r.left, width - w - 8));
    }
    el.style.top = top + window.scrollY + "px";
    el.style.left = left + window.scrollX + "px";
  }

  function scheduleClose(level) {
    var p = previews[level];
    if (!p) return;
    clearTimeout(p.timer);
    p.timer = setTimeout(function () { closePreviews(level); }, CLOSE_DELAY);
  }

  // pointer over a popover keeps it and the ones it opened from
  function cancelClose(level) {
    for (var i = 0; i <= level && i < previews.length; i++) {
      clearTimeout(previews[i].timer);
    }
  }

  function closePreviews(level) {
    while (previews.length > level) {
      var p = previews.pop();
      clearTimeout(p.timer);
      p.el.remove();
    }
  }

  // code blocks are highlighted and mermaid diagrams drawn as they near the window, by libraries loaded
  // from CDNs on first need; offline they stay as written

  var PRISM = "https://cdnjs.cloudflare.com/ajax/libs/prism/1.30.0/";
  var MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@12.2.0/dist/mermaid.esm.min.mjs";
  var PLAIN = /^(text|txt|plain|plaintext)$/;
  var codeObserver = null;
  var prism = null, mermaid = null;  // promises of loaded libraries
  var marked = [];  // blocks that came near with search marks in them, rendering would drop the marks
  var diagrams = 0;

  function bindCode() {
    if (!("IntersectionObserver" in window)) return;
    codeObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        codeObserver.unobserve(e.target);
        renderCode(e.target);
      });
    }, { rootMargin: "400px 0px" });
    codeBlocks(content).forEach(function (pre) { codeObserver.observe(pre); });
  }

  function codeBlocks(root) {
    return Array.prototype.filter.call(root.querySelectorAll("pre:not([data-rendered])"), function (pre) {
      var lang = langOf(pre);
      return lang && !PLAIN.test(lang);
    });
  }

  function langOf(pre) {
    var code = pre.querySelector(":scope > code");
    var m = code && /(?:^|\s)language-(\S+)/.exec(code.className);
    return m ? m[1] : "";
  }

  function renderCode(pre) {
    if (pre.querySelector("mark.hit")) {
      marked.push(pre);
      return;
    }
    pre.dataset.rendered = "";
    if (langOf(pre) === "mermaid") draw(pre);
    else highlight(pre.firstElementChild);
  }

  function renderMarked() {
    if (codeObserver) marked.splice(0).forEach(function (pre) { codeObserver.observe(pre); });
  }

  function highlight(code) {
    loadPrism().then(function (Prism) { Prism.highlightElement(code); }, function () {});
  }

  function loadPrism() {
    if (!prism) {
      window.Prism = { manual: true };
      prism = loadScript(PRISM + "components/prism-core.min.js").then(function () {
        return loadScript(PRISM + "plugins/autoloader/prism-autoloader.min.js");
      }).then(function () {
        window.Prism.plugins.autoloader.languages_path = PRISM + "components/";
        return window.Prism;
      });
    }
    return prism;
  }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  function draw(pre) {
    loadMermaid().then(function (m) {
      return m.render("mermaid-" + ++diagrams, pre.textContent);
    }).then(function (out) {
      var div = document.createElement("div");
      div.className = "mermaid";
      div.innerHTML = out.svg;
      pre.replaceWith(div);
    }, function () {});
  }

  function loadMermaid() {
    if (!mermaid) {
      mermaid = import(MERMAID).then(function (mod) {
        var light = window.matchMedia("(prefers-color-scheme: light)").matches;
        mod.default.initialize({ startOnLoad: false, theme: light ? "default" : "dark" });
        return mod.default;
      });
    }
    return mermaid;
  }

  // numbered list items show their number on hover, a click copies the link to the item;
  // the anchor's id ends with the number path, the page links the anchor to itself

  function bindItems() {
    content.querySelectorAll(".item-anchor").forEach(function (a) {
      a.setAttribute("href", "#" + a.id);
      var m = /--(\d+(?:\.\d+)*)$/.exec(a.id);
      if (m) a.dataset.item = m[1];
    });
    content.addEventListener("click", function (e) {
      var a = e.target.closest(".item-anchor");
      if (!a) return;
      e.preventDefault();
      history.replaceState(null, "", a.getAttribute("href"));
      var done = function () {
        a.classList.add("copied");
        setTimeout(function () { a.classList.remove("copied"); }, 1200);
      };
      try {
        navigator.clipboard.writeText(location.href).then(done, function () {});
      } catch (err) {}
    });
  }

  // sidebar width: dragging its edge sets it, double click restores the default, remembered per browser

  function bindResize() {
    var WIDTH_KEY = "uwiki-sidebar-width";
    var handle = document.getElementById("resize");
    var root = document.documentElement;
    var setWidth = function (px) {
      var max = Math.max(200, window.innerWidth * 0.7);
      root.style.setProperty("--sidebar-width", Math.round(Math.min(Math.max(px, 160), max)) + "px");
    };
    try {
      var saved = +localStorage.getItem(WIDTH_KEY);
      if (saved) setWidth(saved);
    } catch (e) {}
    var dragging = false;
    handle.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      dragging = true;
      handle.setPointerCapture(e.pointerId);
      document.body.classList.add("resizing");
    });
    handle.addEventListener("pointermove", function (e) {
      if (dragging) setWidth(e.clientX);
    });
    handle.addEventListener("lostpointercapture", function () {
      if (!dragging) return;
      dragging = false;
      document.body.classList.remove("resizing");
      try {
        localStorage.setItem(WIDTH_KEY, parseInt(root.style.getPropertyValue("--sidebar-width"), 10));
      } catch (err) {}
    });
    handle.addEventListener("dblclick", function () {
      root.style.removeProperty("--sidebar-width");
      try {
        localStorage.removeItem(WIDTH_KEY);
      } catch (e) {}
    });
  }

  // text size and line spacing of pages and previews: buttons by the title and + - < > keys step them,
  // 0 restores both, remembered per browser; the text at the top of the window stays there

  var SCALE_KEY = "uwiki-text-scale", SPACE_KEY = "uwiki-line-space";
  var MIN_SCALE = 0.6, MAX_SCALE = 2;
  var MIN_SPACE = -0.4, MAX_SPACE = 1;  // added to the line height of 1.6
  var scale = 1, space = 0;

  function bindZoom() {
    try {
      var saved = +localStorage.getItem(SCALE_KEY);
      if (saved) setScale(saved);
      setSpace(+localStorage.getItem(SPACE_KEY) || 0);
    } catch (e) {}
    document.getElementById("smaller").addEventListener("click", function () { zoom(-1, 0); });
    document.getElementById("larger").addEventListener("click", function () { zoom(1, 0); });
    document.getElementById("_tighter").addEventListener("click", function () { zoom(0, -1); });
    document.getElementById("_looser").addEventListener("click", function () { zoom(0, 1); });
    var KEYS = { "+": [1, 0], "=": [1, 0], "-": [-1, 0], "<": [0, -1], ",": [0, -1], ">": [0, 1], ".": [0, 1], "0": [0, 0] };
    document.addEventListener("keydown", function (e) {
      if (e.ctrlKey || e.metaKey || e.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
      var step = KEYS[latinKey(e)];
      if (!step) return;
      e.preventDefault();
      zoom(step[0], step[1]);
    });
  }

  // a step is a tenth of the default size or of a line; no step at all restores both
  function zoom(size, lines) {
    var next = size ? Math.round(scale * 10 + size) / 10 : lines ? scale : 1;
    var gap = lines ? Math.round(space * 10 + lines) / 10 : size ? space : 0;
    next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, next));
    gap = Math.min(MAX_SPACE, Math.max(MIN_SPACE, gap));
    if (next === scale && gap === space) return;
    var anchor = textAtTop();
    var top = anchor && anchor.getBoundingClientRect().top;
    setScale(next);
    setSpace(gap);
    sizePages();
    if (anchor) window.scrollBy(0, anchor.getBoundingClientRect().top - top);
    try {
      if (scale === 1) localStorage.removeItem(SCALE_KEY);
      else localStorage.setItem(SCALE_KEY, scale);
      if (space === 0) localStorage.removeItem(SPACE_KEY);
      else localStorage.setItem(SPACE_KEY, space);
    } catch (e) {}
  }

  // element of page text near the top of the window, under the sticky header of its page
  function textAtTop() {
    var x = content.getBoundingClientRect().left + content.clientWidth / 2, y = 40;
    var el = document.elementFromPoint(x, y);
    var head = el && el.closest(".content > section > .page");
    if (head) el = document.elementFromPoint(x, head.getBoundingClientRect().bottom + 8);
    return el && content.contains(el) && el !== content && !el.closest(".page") ? el : null;
  }

  function setScale(s) {
    scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, s));
    var root = document.documentElement;
    if (scale === 1) root.style.removeProperty("--text-scale");
    else root.style.setProperty("--text-scale", scale);
    document.getElementById("smaller").disabled = scale <= MIN_SCALE;
    document.getElementById("larger").disabled = scale >= MAX_SCALE;
  }

  function setSpace(s) {
    space = Math.min(MAX_SPACE, Math.max(MIN_SPACE, s));
    var root = document.documentElement;
    if (space === 0) root.style.removeProperty("--line-space");
    else root.style.setProperty("--line-space", space);
    document.getElementById("_tighter").disabled = space <= MIN_SPACE;
    document.getElementById("_looser").disabled = space >= MAX_SPACE;
  }

  // help: ? or the button by the title opens it, Esc, a click outside or another ? closes it;
  // a [data-open] button in a box opens that box over it, Esc goes back;
  // the build time shows in local time with how long ago it was

  function bindHelp() {
    var help = document.getElementById("_help_box");
    var button = document.getElementById("_help");
    if (!help.showModal) {
      button.hidden = true;
      return;
    }
    button.addEventListener("click", function () { openBox(help); });
    document.querySelectorAll("dialog.box").forEach(function (box) {
      box.addEventListener("click", function (e) {
        var opener = e.target.closest("[data-open]");
        if (opener) openBox(document.getElementById(opener.dataset.open));
        else if (e.target === box || e.target.closest(".close")) box.close();
      });
    });
    document.addEventListener("keydown", function (e) {
      if (latinKey(e) != "?" || e.ctrlKey || e.metaKey || e.altKey) return;
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
      e.preventDefault();
      if (help.open) closeBoxes();
      else openBox(help);
    });
  }

  function openBox(box) {
    if (previews.length) closePreviews(0);
    var time = box.querySelector("time");
    if (time) showBuilt(time);
    codeBlocks(box).forEach(renderCode);  // config as TOML, highlighted once
    box.showModal();
    (box.querySelector("input") || box).focus();  // the box, not its close button, so no focus ring on open
  }

  function closeBoxes() {
    document.querySelectorAll("dialog.box[open]").forEach(function (box) { box.close(); });
  }

  // go to page: Ctrl K opens a box finding pages and folders by letters of their names in order,
  // the best first: title matches over alias ones over path ones, whole words and starts of words
  // over scattered letters; a page the search hides is shown by clearing the search

  var GOTO_MAX = 50;  // entries listed
  var gotoBox = null, gotoInput = null, gotoList = null, gotoAt = 0;
  var gotoItems = null;  // [{node, title, aliases, path}], made on first open

  function bindGoto() {
    gotoBox = document.getElementById("_goto_box");
    if (!gotoBox.showModal) return;
    gotoInput = gotoBox.querySelector("input");
    gotoList = gotoBox.querySelector("ul");
    gotoInput.addEventListener("input", function () { listGoto(gotoInput.value); });
    gotoInput.addEventListener("keydown", function (e) {
      var down = e.key == "ArrowDown" || (e.ctrlKey && latinKey(e) == "n");
      var up = e.key == "ArrowUp" || (e.ctrlKey && latinKey(e) == "p");
      if (down || up) {
        e.preventDefault();
        selectGoto(gotoAt + (down ? 1 : -1));
      } else if (e.key == "Enter") {
        e.preventDefault();
        var a = gotoList.children[gotoAt] && gotoList.children[gotoAt].firstChild;
        if (a) a.click();
      }
    });
    gotoList.addEventListener("pointermove", function (e) {
      var li = e.target.closest("li");
      if (li) selectGoto(Array.prototype.indexOf.call(gotoList.children, li));
    });
    // before the link is followed: its page shown, the box closed
    gotoList.addEventListener("click", function (e) {
      var a = e.target.closest("a");
      if (!a) return;
      var node = nodeOf.get(document.getElementById(hashId(a.getAttribute("href"))));
      if (node && node.state === "hidden") {
        query.value = "";
        update();
      }
      gotoBox.close();
      document.body.classList.remove("nav-open");
    }, true);
  }

  function openGoto() {
    if (!gotoInput) return;
    if (gotoBox.open) return gotoBox.close();
    closeBoxes();
    if (!gotoItems) {
      gotoItems = nodes.map(function (n) {
        var path = n.info ? n.info.path : crumbOf(n.h);
        return { node: n, title: titleOf(n.h), aliases: (n.h.dataset.aliases || "").toLowerCase(),
                 path: path.toLowerCase() };
      });
    }
    gotoInput.value = "";
    listGoto("");
    openBox(gotoBox);
  }

  function listGoto(q) {
    var terms = q.toLowerCase().split(/\s+/).filter(Boolean);
    var found = [];
    gotoItems.forEach(function (item, i) {
      var res = terms.length ? scoreGoto(item, terms) : { score: 0, at: [] };
      if (res) found.push({ item: item, score: res.score, at: res.at, i: i });
    });
    found.sort(function (a, b) { return b.score - a.score || a.i - b.i; });
    gotoList.textContent = "";
    found.slice(0, GOTO_MAX).forEach(function (f) {
      var li = document.createElement("li");
      li.setAttribute("role", "option");
      var a = document.createElement("a");
      a.href = "#" + f.item.node.h.id;
      a.tabIndex = -1;
      var title = document.createElement("span");
      title.className = "title";
      markLetters(title, f.item.title, f.at);
      a.appendChild(title);
      var where = crumbOf(f.item.node.h);
      if (where) {
        var crumb = document.createElement("span");
        crumb.className = "crumb";
        crumb.textContent = where;
        a.appendChild(crumb);
      }
      if (f.item.node.state === "hidden") a.classList.add("off");
      li.appendChild(a);
      gotoList.appendChild(li);
    });
    if (!found.length) {
      var none = document.createElement("li");
      none.className = "none";
      none.textContent = "no page has these letters in order";
      gotoList.appendChild(none);
    }
    selectGoto(0);
  }

  function selectGoto(i) {
    var items = gotoList.querySelectorAll("li[role=option]");
    if (!items.length) return;
    gotoAt = Math.max(0, Math.min(items.length - 1, i));
    items.forEach(function (li, j) { li.setAttribute("aria-selected", j === gotoAt ? "true" : "false"); });
    items[gotoAt].scrollIntoView({ block: "nearest" });
  }

  // every term in the title, an alias or the path, the best place for each; title letters to mark
  var GOTO_WEIGHTS = { title: 1, aliases: 0.8, path: 0.5 };
  function scoreGoto(item, terms) {
    var total = 0, at = [], inTitle = true;
    var title = item.title.toLowerCase();
    for (var t = 0; t < terms.length; t++) {
      var best = null, where = null;
      ["title", "aliases", "path"].forEach(function (field) {
        var m = fuzzy(terms[t], field === "title" ? title : item[field]);
        if (m && (!best || m.score * GOTO_WEIGHTS[field] > best.score)) {
          best = { score: m.score * GOTO_WEIGHTS[field], at: m.at };
          where = field;
        }
      });
      if (!best) return null;
      total += best.score;
      if (where === "title") at = at.concat(best.at);
      else inTitle = false;
    }
    return { score: total + (inTitle ? 40 : 0) - title.length / 10, at: at };
  }

  // term in s: whole, else its letters in order; score and where the letters are
  var WORD_START = /[\s\-_/.,:()[\]'"›]/;
  function fuzzy(term, s) {
    var i = s.indexOf(term);
    if (i >= 0) {
      var at = [];
      for (var k = 0; k < term.length; k++) at.push(i + k);
      var start = i === 0 || WORD_START.test(s[i - 1]);
      return { score: 100 + 12 * term.length + (i === 0 ? 40 : start ? 25 : 0) + (term === s ? 60 : 0), at: at };
    }
    return letters(term, s, true) || letters(term, s, false);
  }

  // letters in order, preferring for each one right after the last or at a start of a word,
  // which can skip past letters the rest needs, so then the earliest ones
  function letters(term, s, prefer) {
    var res = [], score = 0, from = 0;
    for (var j = 0; j < term.length; j++) {
      var c = term[j], pos = -1;
      for (var p = from; p < s.length; p++) {
        if (s[p] !== c) continue;
        if (pos < 0) pos = p;
        if (!prefer) break;
        if (p === res[res.length - 1] + 1 || p === 0 || WORD_START.test(s[p - 1])) {
          pos = p;
          break;
        }
      }
      if (pos < 0) return null;
      var after = res.length && pos === res[res.length - 1] + 1;
      score += 4 + (after ? 8 : 0) + (pos === 0 || WORD_START.test(s[pos - 1]) ? 7 : 0);
      res.push(pos);
      from = pos + 1;
    }
    return { score: score - (res[res.length - 1] - res[0] + 1 - term.length) / 2, at: res };
  }

  function markLetters(el, text, at) {
    var set = new Set(at), run = "", inMark = false;
    var flush = function () {
      if (!run) return;
      if (inMark) {
        var b = document.createElement("b");
        b.textContent = run;
        el.appendChild(b);
      } else {
        el.appendChild(document.createTextNode(run));
      }
      run = "";
    };
    for (var i = 0; i < text.length; i++) {
      if (set.has(i) !== inMark) {
        flush();
        inMark = !inMark;
      }
      run += text[i];
    }
    flush();
  }

  // the key as a US layout has it where the layout types no Latin there, as a Cyrillic one does: shortcuts
  // go by what a key types in Latin layouts, Dvorak too, else by the key; Cyrillic layouts type . on the / key
  var CODE_KEYS = { BracketLeft: "[{", BracketRight: "]}", Slash: "/?", Comma: ",<", Period: ".>",
                    Semicolon: ";:", Quote: "'\"", Backquote: "`~", Minus: "-_", Equal: "=+" };
  function latinKey(e) {
    var key = e.key || "";
    var byCode = key.length === 1 && !/[ -~]/.test(key) || e.code === "Slash" && (key === "." || key === ",");
    if (!byCode) return key;
    var letter = /^Key([A-Z])$/.exec(e.code || ""), pair = CODE_KEYS[e.code];
    if (letter) return e.shiftKey ? letter[1] : letter[1].toLowerCase();
    return pair ? pair[e.shiftKey ? 1 : 0] : key;
  }

  // reading keys: j and k go to the next and previous page, t to the top, [ and ] fold and unfold the tree,
  // u up to the page the logo links to, when built with --up
  function bindReading() {
    document.addEventListener("keydown", function (e) {
      if (e.ctrlKey || e.metaKey || e.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)
          || document.querySelector("dialog.box[open]")) return;
      var key = latinKey(e);
      if (key == "j" || key == "k") pageStep(key == "j" ? 1 : -1);
      else if (key == "t") window.scrollTo(0, 0);
      else if (key == "u" && document.getElementById("up")) location.href = document.getElementById("up").href;
      else if (key == "[" || key == "]") foldAll(key == "[");
      else return;
      e.preventDefault();
    });
  }

  // from the page being read, as spy finds it; back from inside a page goes to its start first
  function pageStep(dir) {
    var list = shownPages;
    var lo = 0, hi = list.length - 1, cur = -1;
    while (lo <= hi) {
      var mid = (lo + hi) >> 1;
      if (topOf(list[mid]) <= 80) {
        cur = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    var i = dir > 0 ? cur + 1 : cur >= 0 && topOf(list[cur]) < -8 ? cur : cur - 1;
    if (i < 0) window.scrollTo(0, 0);
    else if (i < list.length) jumpTo(list[i]);
  }

  function showBuilt(time) {
    var at = new Date(time.getAttribute("datetime"));
    if (isNaN(at)) return;
    var pad = function (n) { return (n < 10 ? "0" : "") + n; };
    var text = at.getFullYear() + "-" + pad(at.getMonth() + 1) + "-" + pad(at.getDate()) + " " + pad(at.getHours()) + ":" + pad(at.getMinutes());
    time.textContent = text + " (" + ago((Date.now() - at) / 1000) + ")";
    time.title = at.toString();
  }

  // seconds as the largest whole unit, "3 hours ago"
  function ago(s) {
    if (s < 60) return "just now";
    var units = [["year", 31557600], ["month", 2629800], ["week", 604800], ["day", 86400], ["hour", 3600], ["minute", 60]];
    for (var i = 0; i < units.length; i++) {
      var n = Math.floor(s / units[i][1]);
      if (n >= 1) return n + " " + units[i][0] + (n > 1 ? "s" : "") + " ago";
    }
  }

  // events

  function bindEvents() {
    var ticking = false;
    var schedule = function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        ticking = false;
        spy();
      });
    };
    window.addEventListener("scroll", schedule, { passive: true });
    // capture, so the header is measured or a page header unstuck before the browser jumps to the link target
    document.addEventListener("click", function (e) {
      var a = e.target.closest && e.target.closest('a[href^="#"]');
      if (!a) return;
      var id = hashId(a.getAttribute("href"));
      clearHead(id);
      unstick(id);
    }, true);
    // pages drawn as they near the window get their real size, moving the pages after them without a scroll
    if ("ResizeObserver" in window) {
      var resized = new ResizeObserver(schedule);
      content.querySelectorAll(":scope > section").forEach(function (box) { resized.observe(box); });
    }

    query.addEventListener("input", update);
    document.getElementById("clear").addEventListener("click", function () {
      query.value = "";
      update();
      query.focus();
    });
    query.addEventListener("keydown", function (e) {
      if (e.key == "Enter") {
        e.preventDefault();
        step(e.shiftKey ? -1 : 1);
        document.body.classList.remove("nav-open");
      } else if (e.key == "Escape") {
        e.preventDefault();
        escape();
      }
    });

    document.addEventListener("keydown", function (e) {
      var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
      var key = latinKey(e);
      if (key == "k" && (e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey) {
        e.preventDefault();
        openGoto();
      } else if (key == "/" && !typing) {
        e.preventDefault();
        closeBoxes();
        document.body.classList.add("nav-open");
        query.focus();
        query.select();
      } else if (key == "x" && !typing && !e.ctrlKey && !e.metaKey && !e.altKey && query.value
                 && !document.querySelector("dialog.box[open]")) {
        e.preventDefault();
        query.value = "";
        update();
      }
    });

    fold.addEventListener("click", foldAll);
    problems.addEventListener("click", function () { toggleTerm("is", "problem", isProblemTerm); });

    document.getElementById("menu").addEventListener("click", function () {
      document.body.classList.toggle("nav-open");
    });
    sidebar.addEventListener("click", function (e) {
      if (e.target.closest("#toc a, #home")) document.body.classList.remove("nav-open");
    });
  }

  // after all declarations above, constants among them
  bindResize();
  bindZoom();
  bindHelp();
  bindReading();
  bindGoto();
  sizePages();
  floatAsides();
  markBoxDrawing();
  buildTree(toc, headerTree(document.querySelectorAll("h2.page, h3.page, h4.page, h5.page, h6.page")), tocEntry, updateFold);
  readNodes();
  showSizes();
  buildFacets();
  bindEvents();
  if (location.hash) clearHead(hashId(location.hash));
  bindPreviews();
  bindItems();
  bindCode();
  restoreQuery();
  spy();
  // search index and links to pages, built when the page is idle so the first search and filter are quick
  if ("requestIdleCallback" in window) {
    requestIdleCallback(function () { if (!sections) buildIndex(); }, { timeout: 3000 });
    requestIdleCallback(function () { refsOf(null); }, { timeout: 3000 });
  }
})();
