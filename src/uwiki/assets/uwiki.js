(function () {
  "use strict";

  var WORD = /[\p{L}\p{N}]+/gu;
  var WORD_SPLIT = /([\p{L}\p{N}]+)/u;
  var MAX_RESULTS = 50;

  var content = document.querySelector(".content");
  var sidebar = document.getElementById("sidebar");
  var toc = document.getElementById("toc");
  var query = document.getElementById("query");
  var results = document.getElementById("results");
  var pages = Array.prototype.slice.call(document.querySelectorAll(".content .page"));
  var tocLinks = {};
  var active = null;
  var sections = [];
  var vocab = new Map();
  var termCache = new Map();
  var found = [];
  var selected = -1;

  addCrumbs();
  processHeaders(toc, document.querySelectorAll("h2.page, h3.page, h4.page, h5.page, h6.page"), 0);
  buildIndex();
  bindEvents();
  spy();

  // page header "Folder / Page" shows folder as a crumb above page title
  function addCrumbs() {
    pages.forEach(function (h) {
      var text = h.textContent;
      var k = text.lastIndexOf(" / ");
      h.dataset.title = k < 0 ? text : text.slice(k + 3);
      if (k < 0) return;
      var crumb = document.createElement("span");
      crumb.className = "crumb";
      crumb.textContent = text.slice(0, k);
      h.textContent = h.dataset.title;
      h.insertBefore(crumb, h.firstChild);
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

  function toggle(li) {
    var button = document.createElement("button");
    button.className = "toggle";
    button.type = "button";
    button.setAttribute("aria-label", "Toggle section");
    button.textContent = "▼";
    button.addEventListener("click", function () {
      li.classList.toggle("collapsed");
      delete li.dataset.auto;
    });
    return button;
  }

  // highlights TOC entry of the page being read, unfolds its branch
  function spy() {
    var lo = 0, hi = pages.length - 1, current = pages[0];
    while (lo <= hi) {
      var mid = (lo + hi) >> 1;
      if (pages[mid].getBoundingClientRect().top <= 80) {
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
    if (!a) return;
    a.classList.add("active");
    for (var li = a.parentNode.parentNode.closest("li"); li && toc.contains(li); li = li.parentNode.closest("li")) {
      if (li.classList.contains("collapsed")) {
        li.classList.remove("collapsed");
        li.dataset.auto = "";
      }
    }
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
        text: range.toString().replace(/\s+/g, " ").trim(),
        headWords: new Set(words(titleOf(h))),
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

  function search(q) {
    var terms = Array.from(new Set(words(q)));
    if (!terms.length) return [];
    var hits = new Map();
    terms.forEach(function (t, ti) {
      matchTerm(t).forEach(function (m) {
        vocab.get(m[0]).forEach(function (si) {
          var hit = hits.get(si);
          if (!hit) hits.set(si, hit = { index: si, scores: new Array(terms.length).fill(0), words: new Set() });
          // words in the heading and repeated ones weigh more
          var s = sections[si];
          var sim = m[1] * (1 + (s.headWords.has(m[0]) ? 0.6 : 0) + 0.15 * Math.log2(s.counts.get(m[0])));
          hit.scores[ti] = Math.max(hit.scores[ti], sim);
          hit.words.add(m[0]);
        });
      });
    });
    var phrase = terms.length > 1 ? q.trim().toLowerCase().replace(/\s+/g, " ") : "";
    var res = [];
    hits.forEach(function (hit) {
      if (hit.scores.indexOf(0) >= 0) return;
      var s = sections[hit.index];
      hit.score = hit.scores.reduce(function (a, b) { return a + b; }, 0);
      if (phrase && (s.lower.includes(phrase) || s.title.toLowerCase().includes(phrase))) hit.score += 1;
      if (s.head === s.page) hit.score += 0.2;
      res.push(hit);
    });
    return res.sort(function (a, b) { return b.score - a.score || a.index - b.index; });
  }

  // results

  function update() {
    clearMarks();
    var q = query.value;
    if (!q.trim()) {
      results.hidden = true;
      toc.hidden = false;
      found = [];
      return;
    }
    found = search(q);
    results.textContent = "";
    results.scrollTop = 0;
    found.slice(0, MAX_RESULTS).forEach(function (hit, i) {
      var s = sections[hit.index];
      var a = document.createElement("a");
      a.href = "#" + s.head.id;
      a.dataset.index = i;
      var title = document.createElement("span");
      title.className = "result-title";
      title.appendChild(markUp(s.title, hit.words));
      a.appendChild(title);
      if (s.page && s.page !== s.head) {
        var path = document.createElement("span");
        path.className = "result-path";
        path.textContent = " — " + titleOf(s.page);
        a.appendChild(path);
      }
      var snip = document.createElement("span");
      snip.className = "result-snippet";
      snip.appendChild(snippet(s.text, hit.words));
      a.appendChild(snip);
      results.appendChild(a);
    });
    if (!found.length) {
      var empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "No matches";
      results.appendChild(empty);
    }
    results.hidden = false;
    toc.hidden = true;
    select(found.length ? 0 : -1);
  }

  function snippet(text, hits) {
    var parts = text.split(WORD_SPLIT), pos = 0, first = -1;
    for (var i = 0; i < parts.length; i++) {
      if (i % 2 && hits.has(parts[i].toLowerCase())) {
        first = pos;
        break;
      }
      pos += parts[i].length;
    }
    var start = Math.max(0, first - 60);
    if (start > 0) {
      var space = text.indexOf(" ", start);
      if (space >= 0 && space < first) start = space + 1;
    }
    var end = Math.min(text.length, start + 180);
    if (end < text.length) {
      var back = text.lastIndexOf(" ", end);
      if (back > first) end = back;
    }
    var piece = (start > 0 ? "…" : "") + text.slice(start, end) + (end < text.length ? "…" : "");
    return markUp(piece, hits);
  }

  // text with hit words wrapped in <mark>, null when there are none
  function markUp(text, hits, onlyHits) {
    var frag = document.createDocumentFragment();
    var marked = false;
    text.split(WORD_SPLIT).forEach(function (part, i) {
      if (!part) return;
      if (i % 2 && hits.has(part.toLowerCase())) {
        var mark = document.createElement("mark");
        mark.className = "hit";
        mark.textContent = part;
        frag.appendChild(mark);
        marked = true;
      } else {
        frag.appendChild(document.createTextNode(part));
      }
    });
    return marked || !onlyHits ? frag : null;
  }

  function select(i) {
    var links = results.querySelectorAll("a");
    if (selected >= 0 && links[selected]) links[selected].classList.remove("selected");
    selected = Math.max(-1, Math.min(i, links.length - 1));
    if (selected < 0) return;
    links[selected].classList.add("selected");
    links[selected].scrollIntoView({ block: "nearest" });
  }

  // jumps to the section and marks matched words in its text
  function open(i) {
    var hit = found[i];
    if (!hit) return;
    select(i);
    clearMarks();
    var s = sections[hit.index];
    var range = document.createRange();
    range.setStartBefore(s.head);
    if (s.next) {
      range.setEndBefore(s.next);
    } else {
      range.setEnd(content, content.childNodes.length);
    }
    var nodes = [];
    var walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      if (range.intersectsNode(walker.currentNode)) nodes.push(walker.currentNode);
    }
    nodes.forEach(function (node) {
      var frag = markUp(node.data, hit.words, true);
      if (frag) node.parentNode.replaceChild(frag, node);
    });
    history.replaceState(null, "", "#" + s.head.id);
    var mark = content.querySelector("mark.hit");
    var target = mark && !s.head.contains(mark) ? mark : s.head;
    target.scrollIntoView({ block: target === mark ? "center" : "start" });
    var details = target.closest("details");
    if (details) details.open = true;
    document.body.classList.remove("nav-open");
  }

  function clearMarks() {
    content.querySelectorAll("mark.hit").forEach(function (mark) {
      var parent = mark.parentNode;
      parent.replaceChild(document.createTextNode(mark.textContent), mark);
      parent.normalize();
    });
  }

  // events

  function bindEvents() {
    var ticking = false;
    window.addEventListener("scroll", function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        ticking = false;
        spy();
      });
    }, { passive: true });

    query.addEventListener("input", update);
    query.addEventListener("keydown", function (e) {
      if (e.key == "ArrowDown" || e.key == "ArrowUp") {
        e.preventDefault();
        select(selected + (e.key == "ArrowDown" ? 1 : -1));
      } else if (e.key == "Enter") {
        e.preventDefault();
        open(Math.max(selected, 0));
      } else if (e.key == "Escape") {
        if (query.value) {
          query.value = "";
          update();
        } else {
          query.blur();
        }
      }
    });

    results.addEventListener("click", function (e) {
      var a = e.target.closest("a");
      if (!a) return;
      e.preventDefault();
      open(+a.dataset.index);
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

    document.getElementById("menu").addEventListener("click", function () {
      document.body.classList.toggle("nav-open");
    });
    sidebar.addEventListener("click", function (e) {
      if (e.target.closest("#toc a, #home")) document.body.classList.remove("nav-open");
    });
  }
})();
