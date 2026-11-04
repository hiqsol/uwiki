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
  var fold = document.getElementById("fold");
  var pages = Array.prototype.slice.call(document.querySelectorAll(".content .page"));
  var tocLinks = {};
  var active = null;
  var sections = null;  // search index, built on first search
  var vocab = new Map();
  var termCache = new Map();
  var found = [];
  var selected = -1;

  bindResize();
  addCrumbs();
  markBoxDrawing();
  processHeaders(toc, document.querySelectorAll("h2.page, h3.page, h4.page, h5.page, h6.page"), 0);
  bindEvents();
  bindPreviews();
  bindItems();
  spy();

  // page header "Folder / Subfolder / Page" shows folders as a crumb above page title,
  // backlinks and front matter blocks go before them, floating right one over the other
  function addCrumbs() {
    pages.forEach(function (h) {
      var blocks = Array.prototype.slice.call(h.querySelectorAll(":scope > details"));
      blocks.forEach(function (block) { h.removeChild(block); });
      var text = h.textContent;
      var crumb = null;
      if (h.dataset.title && h.dataset.title !== text) {
        crumb = document.createElement("span");
        crumb.className = "crumb";
        crumb.textContent = text.slice(0, text.length - h.dataset.title.length - 3);
        h.textContent = h.dataset.title;
        h.insertBefore(crumb, h.firstChild);
      }
      blocks.reverse().forEach(function (block) { h.insertBefore(block, h.firstChild); });
    });
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

  function toggle(li) {
    var button = document.createElement("button");
    button.className = "toggle";
    button.type = "button";
    button.setAttribute("aria-label", "Toggle section");
    button.textContent = "▼";
    button.addEventListener("click", function () {
      li.classList.toggle("collapsed");
      delete li.dataset.auto;
      updateFold();
    });
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
    frag.querySelectorAll(".backlinks").forEach(function (el) { el.remove(); });
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

  function search(q) {
    var terms = Array.from(new Set(words(q)));
    if (!terms.length) return [];
    if (!sections) buildIndex();
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
    walker.currentNode = s.head;
    while (walker.nextNode() && range.intersectsNode(walker.currentNode)) nodes.push(walker.currentNode);
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
    if (!a || !a.closest("main.content, .preview") || a.closest(".preview-title")) return null;
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
    el.appendChild(title);
    var body = document.createElement("div");
    body.className = "content preview-body";
    sectionOf(target).forEach(function (node) {
      var copy = node.cloneNode(true);
      copy.removeAttribute("id");
      copy.querySelectorAll("[id]").forEach(function (n) { n.removeAttribute("id"); });
      body.appendChild(copy);
    });
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
      if (!n.classList.contains("backlinks")) nodes.push(n);
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

  function pageOf(el) {
    var page = null;
    for (var i = 0; i < pages.length && pages[i].compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING; i++) {
      page = pages[i];
    }
    return page;
  }

  // under the link, above it when there is no room below, inside the window
  function place(el, a) {
    var r = a.getClientRects()[0] || a.getBoundingClientRect();
    var h = el.offsetHeight, w = el.offsetWidth;
    var top = r.bottom + 6;
    if (top + h > window.innerHeight && r.top - h - 6 > 0) top = r.top - h - 6;
    var left = Math.max(8, Math.min(r.left, document.documentElement.clientWidth - w - 8));
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

  // numbered list items show their number on hover, a click copies the link to the item

  function bindItems() {
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

    fold.addEventListener("click", foldAll);

    document.getElementById("menu").addEventListener("click", function () {
      document.body.classList.toggle("nav-open");
    });
    sidebar.addEventListener("click", function (e) {
      if (e.target.closest("#toc a, #home")) document.body.classList.remove("nav-open");
    });
  }
})();
