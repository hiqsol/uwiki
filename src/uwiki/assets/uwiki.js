(function () {
  "use strict";

  var WORD = /[\p{L}\p{N}]+/gu;
  var WORD_SPLIT = /([\p{L}\p{N}]+)/u;
  var MAX_HITS = 30;  // sections listed under a page in the sidebar
  var URL_KEY = "q";

  var content = document.querySelector(".content");
  var sidebar = document.getElementById("sidebar");
  var toc = document.getElementById("toc");
  var query = document.getElementById("query");
  var stats = document.getElementById("stats");
  var facets = document.getElementById("facets");
  var fold = document.getElementById("fold");
  var pages = Array.prototype.slice.call(document.querySelectorAll(".content .page"));
  var data = readData();
  var tocLinks = {};
  var active = null;
  var sections = null;  // search index, built on first search
  var vocab = new Map();
  var termCache = new Map();
  var nodes = [];  // page headers in order with their tree, elements and state
  var nodeOf = new Map();  // page header: node
  var refs = new Map();  // page header: links to it and backlink titles naming it
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

  // problems the page has, backlinks and front matter blocks built from the data go before crumb and title,
  // floating right one over the other
  function floatAsides() {
    pages.forEach(function (h) {
      var blocks = Array.prototype.slice.call(h.querySelectorAll(":scope > details"));
      var info = data.pages[h.id];
      blocks.push(backlinksBlock(data.backlinks[h.id] || []));
      if (info && data.frontMatter !== false) blocks.push(frontMatterBlock(info));
      blocks.filter(Boolean).reverse().forEach(function (block) { h.insertBefore(block, h.firstChild); });
    });
  }

  // folded line of backlink titles, readRefs fills it, unfolding into links to the linking pages
  function backlinksBlock(links) {
    if (!links.length) return null;
    var block = details("backlinks");
    var summary = block.firstChild, div = document.createElement("div");
    var b = document.createElement("b");
    b.textContent = "Backlinks (" + links.length + "):";
    summary.appendChild(b);
    summary.appendChild(document.createElement("span"));
    links.forEach(function (link, i) {
      var anchor = Array.isArray(link) ? link[0] : link, heading = Array.isArray(link) ? link[1] : "";
      var source = document.getElementById(anchor);
      var a = document.createElement("a");
      a.href = "#" + anchor;
      a.textContent = (source ? titleOf(source) : anchor) + (heading ? " › " + heading : "");
      if (i) div.appendChild(document.createTextNode(", "));
      div.appendChild(a);
    });
    block.appendChild(div);
    return block;
  }

  // front matter as folded line of values unfolding into one table of keys and values:
  // a nested key beside the key above it spanning its rows, a list of maps an item after another;
  // none for title only
  function frontMatterBlock(info) {
    var items = {}, nested = info.nested || {};
    Object.keys(info.meta).forEach(function (key) { items[key] = key in nested ? nested[key] : info.meta[key]; });
    var line = Object.keys(items).filter(function (key) { return key !== "title"; }).map(function (key) {
      return frontText(items[key]);
    }).filter(Boolean).join(" · ");
    if (!line) return null;
    var block = details("front-matter" + (info.frontProblem ? " problem" : ""));
    var span = document.createElement("span");
    span.textContent = line;
    block.firstChild.appendChild(span);
    block.appendChild(frontTable(items));
    return block;
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

  function processHeaders(parent, headers, i) {
    var first = headers[i];
    var li = null;
    while (i < headers.length) {
      var h = headers[i];
      if (!h.id) {
        i++;
      } else if (h.tagName[1] == first.tagName[1]) {
        li = document.createElement("li");
        var a = document.createElement("a");
        a.href = "#" + h.id;
        a.textContent = a.title = titleOf(h);
        tocLinks[h.id] = a;
        li.appendChild(a);
        parent.appendChild(li);
        i++;
      } else if (h.tagName[1] > first.tagName[1]) {
        var ul = document.createElement("ul");
        li.appendChild(ul);
        li.classList.add("collapsed");
        li.insertBefore(toggle(li), li.firstChild);
        i = processHeaders(ul, headers, i);
      } else {
        return i;
      }
    }
    return i;
  }

  // the button and the title link of a branch both fold and unfold it, the link also goes to its page
  function toggle(li) {
    var button = document.createElement("button");
    button.className = "toggle";
    button.type = "button";
    button.setAttribute("aria-label", "Toggle section");
    button.textContent = "▼";
    var flip = function () {
      li.classList.toggle("collapsed");
      delete li.dataset.auto;
      updateFold();
    };
    button.addEventListener("click", flip);
    li.querySelector(":scope > a").addEventListener("click", flip);
    return button;
  }

  // one button for the whole tree: expands all when any branch is collapsed, else collapses all
  function updateFold() {
    var branches = toc.querySelectorAll("li > .toggle");
    fold.hidden = !branches.length;
    fold.textContent = toc.querySelector("li.collapsed") ? "Expand all" : "Collapse all";
  }

  function foldAll() {
    var collapse = !toc.querySelector("li.collapsed");
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
      box.style.containIntrinsicSize = "auto " + Math.round(info ? 230 + 1900 * info.words / width : 70) + "px";
    });
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
    var r = a.getBoundingClientRect(), t = toc.getBoundingClientRect();
    if (r.top < t.top || r.bottom > t.bottom) {
      toc.scrollTop += r.top - t.top - t.height / 3;
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

  // text of the range without parts added by build, as "Backlinks"
  function textOf(range) {
    var frag = range.cloneContents();
    frag.querySelectorAll(".backlinks, .problems").forEach(function (el) { el.remove(); });
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

  // links to pages and backlink titles, greyed when their page is filtered out
  function readRefs() {
    var pageOfId = new Map(), cur = null;
    content.querySelectorAll("[id]").forEach(function (el) {
      if (el.classList.contains("page")) cur = el;
      pageOfId.set(el.id, cur);
    });
    var target = function (a) { return pageOfId.get(decodeURIComponent(a.getAttribute("href").slice(1))); };
    var add = function (el, page) {
      if (!refs.has(page)) refs.set(page, []);
      refs.get(page).push(el);
    };
    content.querySelectorAll("a[href^='#']").forEach(function (a) {
      var page = !a.classList.contains("item-anchor") && target(a);
      if (page) add(a, page);
    });
    content.querySelectorAll(".problems a").forEach(function (a) {
      var id = decodeURIComponent(a.getAttribute("href").slice(1));
      if (!document.getElementById(id)) a.setAttribute("href", "#" + id.replace(/^problem-(.*)-\d+$/, "$1"));
    });
    content.querySelectorAll(".backlinks").forEach(function (block) {
      var line = block.querySelector(":scope > summary > span");
      var links = block.querySelectorAll(":scope > div > a");
      if (!line || !links.length) return;
      line.textContent = "";
      links.forEach(function (a, i) {
        if (i) line.appendChild(document.createTextNode(", "));
        var title = document.createElement("span");
        title.textContent = a.textContent;
        line.appendChild(title);
        var page = target(a);
        if (page) add(title, page);
      });
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

  // value matches exactly when the vault has it, else by prefix, so a value being typed already filters
  function matcher(t) {
    if (t.key === "in") return folderMatcher(t.value.replace(/\/+$/, ""));
    if (t.key === "is") return problemMatcher(t.value);
    var exact = valueSet(t.key).has(t.value);
    return function (node) {
      return valuesOf(node, t.key).some(function (v) { return exact ? v === t.value : v.startsWith(t.value); });
    };
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
    showHits(prep, matched);
    showStats(matched, filtering);
    showFacets(prep);
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
        (refs.get(n.h) || []).forEach(function (el) { el.classList.toggle("off", n.next === "hidden"); });
      }
      n.state = n.next;
      n.h.hidden = n.state === "hidden";
      if (boxOf(n.h) !== n.h) boxOf(n.h).hidden = n.state === "hidden";
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
    var problems = sum(matched, "problems");
    stats.textContent = cols.map(function (c) {
      return (filtering ? short(c[1]) + "/" : "") + short(c[2]) + " " + c[0];
    }).join(" · ") + (problems ? " · " + problems + " problems" : "");
    stats.title = cols.map(function (c) { return (filtering ? c[1] + " of " : "") + c[2] + " " + c[0]; }).join(", ");
  }

  function short(n) {
    if (n < 1000) return String(n);
    if (n < 10000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
    return Math.round(n / 1000) + "k";
  }

  // facet chips: a row for every schema key listing values, a chip per value with the count of pages
  // it shows with the other terms of the box

  var FOLDED_KEY = "uwiki-folded-facets";

  function buildFacets() {
    var folded = [];
    try {
      folded = JSON.parse(localStorage.getItem(FOLDED_KEY) || "[]");
    } catch (e) {}
    data.facets.forEach(function (facet) {
      var row = document.createElement("div");
      row.className = "facet" + (folded.indexOf(facet[0]) >= 0 ? " folded" : "");
      row.dataset.key = facet[0];
      var name = document.createElement("button");
      name.type = "button";
      name.className = "facet-key";
      name.textContent = facet[0];
      name.title = "Fold or unfold " + facet[0];
      row.appendChild(name);
      facet[1].forEach(function (value) {
        var chip = document.createElement("button");
        chip.type = "button";
        chip.className = "chip";
        chip.dataset.value = value;
        chip.textContent = value;
        chip.appendChild(document.createElement("span"));
        row.appendChild(chip);
      });
      facets.appendChild(row);
    });
    facets.hidden = !data.facets.length;
    facets.addEventListener("click", function (e) {
      var row = e.target.closest(".facet");
      if (!row) return;
      if (e.target.closest(".facet-key")) {
        row.classList.toggle("folded");
        var keys = Array.prototype.map.call(facets.querySelectorAll(".facet.folded"), function (r) { return r.dataset.key; });
        try {
          localStorage.setItem(FOLDED_KEY, JSON.stringify(keys));
        } catch (err) {}
        return;
      }
      var chip = e.target.closest(".chip");
      if (chip) toggleTerm(row.dataset.key, chip.dataset.value);
    });
  }

  function showFacets(prep) {
    facets.querySelectorAll(".facet").forEach(function (row) {
      var key = row.dataset.key;
      var others = match(prep, key);
      var on = new Set(prep.terms.filter(function (t) {
        return t.kind === "key" && t.key === key && !t.neg;
      }).map(function (t) { return t.value; }));
      row.querySelectorAll(".chip").forEach(function (chip) {
        var value = chip.dataset.value.toLowerCase();
        var n = others.filter(function (node) { return valuesOf(node, key).indexOf(value) >= 0; }).length;
        chip.lastChild.textContent = n;
        chip.classList.toggle("zero", !n);
        chip.classList.toggle("on", on.has(value));
      });
    });
  }

  // adds key:value to the box, or removes it when there
  function toggleTerm(key, value) {
    var q = query.value;
    var found = parse(q).filter(function (t) {
      return t.kind === "key" && t.key === key && !t.neg && t.value === value.toLowerCase();
    });
    if (found.length) {
      found.reverse().forEach(function (t) { q = q.slice(0, t.at) + q.slice(t.at + t.raw.length); });
      q = q.replace(/\s+/g, " ").trim();
    } else {
      q = (q.trim() + " " + key + ":" + (/[\s"]/.test(value) ? '"' + value + '"' : value)).trim();
    }
    query.value = q;
    update();
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
        if (!parent.closest(".backlinks, .problems, .front-matter, .crumb, .item-anchor, .mermaid")) {
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
      var target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
      if (target) target.scrollIntoView();
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
    el.appendChild(title);
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
    var p = { el: el, link: a, timer: null };
    previews[level] = p;
    el.addEventListener("pointerenter", function () { cancelClose(previews.indexOf(p)); });
    el.addEventListener("pointerleave", function (e) {
      if (e.pointerType === "mouse") scheduleClose(previews.indexOf(p));
    });
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
      if (!n.classList.contains("backlinks") && !n.classList.contains("problems")) nodes.push(n);
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
    // pages drawn as they near the window get their real size, moving the pages after them without a scroll
    if ("ResizeObserver" in window) {
      var resized = new ResizeObserver(schedule);
      content.querySelectorAll(":scope > section").forEach(function (box) { resized.observe(box); });
    }

    query.addEventListener("input", update);
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
      if ((e.key == "/" && !typing) || (e.key == "k" && (e.ctrlKey || e.metaKey))) {
        e.preventDefault();
        document.body.classList.add("nav-open");
        query.focus();
        query.select();
      }
    });

    fold.addEventListener("click", foldAll);

    document.getElementById("menu").addEventListener("click", function () {
      document.body.classList.toggle("nav-open");
    });
    sidebar.addEventListener("click", function (e) {
      if (e.target.closest("#toc a, #home")) document.body.classList.remove("nav-open");
    });
  }

  // after all declarations above, constants among them
  bindResize();
  sizePages();
  floatAsides();
  markBoxDrawing();
  processHeaders(toc, document.querySelectorAll("h2.page, h3.page, h4.page, h5.page, h6.page"), 0);
  readNodes();
  readRefs();
  buildFacets();
  bindEvents();
  bindPreviews();
  bindItems();
  bindCode();
  restoreQuery();
  spy();
})();
