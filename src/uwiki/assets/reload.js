
// live reload, added by uwiki serve and build --live: reloads after a rebuild, keeps scroll position and search;
// the position is the page at the top of the window and how far into it, as pages far from the window
// have sizes estimated till drawn.
// serve: the server tells the id of its last build; page: a web server serving the built file tells
// its Last-Modified, newer than the one this page came with after a rebuild
(function () {
  "use strict";
  var BUILD = "{build}";
  var SERVE = "{mode}" === "serve";
  var KEY = "uwiki-reload";
  if (!SERVE && !/^https?:$/.test(location.protocol)) return;  // a file opened from disk has no server to ask
  var query = document.getElementById("query");

  function position() {
    var boxes = document.querySelectorAll(".content > section");
    for (var i = 0; i < boxes.length; i++) {
      var r = boxes[i].getBoundingClientRect();
      if (!boxes[i].hidden && r.bottom > 0) return { page: boxes[i].firstElementChild.id, offset: -r.top };
    }
    return {};
  }

  // pages drawn near the window get their real sizes and move the page, so a few frames correct the scroll
  function restore(saved, frames) {
    var h = saved.page && document.getElementById(saved.page);
    if (!h) return window.scrollTo(saved.x, saved.y);
    var off = h.parentNode.getBoundingClientRect().top + saved.offset;
    if (Math.abs(off) >= 1) window.scrollTo(saved.x, window.scrollY + off);
    if (frames > 0 && Math.abs(off) >= 1) requestAnimationFrame(function () { restore(saved, frames - 1); });
  }

  try {
    var saved = JSON.parse(sessionStorage.getItem(KEY) || "null");
    sessionStorage.removeItem(KEY);
    if (saved) {
      if (saved.q) {
        query.value = saved.q;
        query.dispatchEvent(new Event("input"));
      }
      requestAnimationFrame(function () { restore(saved, 10); });
    }
  } catch (e) {}

  // the help tells whether the server answers, since when not
  var live = document.querySelector("#_help_box .live");
  var lost = null;
  function status(ok) {
    if (!live) return;
    if (!ok && !lost) lost = new Date();
    if (ok) lost = null;
    live.hidden = false;
    live.classList.toggle("lost", !ok);
    live.textContent = ok ? (SERVE ? "Live: served by uwiki serve, reloads when a page changes."
                                   : "Live: reloads when the wiki is built again.")
      : "Live: the server has not answered since " + lost.toTimeString().slice(0, 5) + ", trying again.";
  }
  status(true);

  // the page as served now: the last-modified time of the file, in whole seconds as HTTP gives it,
  // this page's from document.lastModified, filled from the same header when it came
  var shown = Date.parse(document.lastModified);
  var reloaded = null;
  try { reloaded = Number(sessionStorage.getItem(KEY + "-to")) || null; } catch (e) {}
  function changed() {
    if (SERVE) {
      return fetch("/__uwiki/build", { cache: "no-store" }).then(function (r) {
        return r.ok && r.text().then(function (build) { return build !== BUILD; });
      });
    }
    return fetch(location.pathname + location.search, { method: "HEAD", cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      var modified = Date.parse(r.headers.get("Last-Modified") || "");
      // a reload that brought no newer page, as from a cache in the way, is not tried again for the same time
      if (isNaN(modified) || isNaN(shown) || modified <= shown || modified === reloaded) return false;
      try { sessionStorage.setItem(KEY + "-to", String(modified)); } catch (e) {}
      return true;
    });
  }

  var EVERY = SERVE ? 700 : 5000;
  var timer = null;
  function later(ms) {
    clearTimeout(timer);
    timer = document.hidden && !SERVE ? null : setTimeout(check, ms);
  }
  function check() {
    timer = null;
    changed().then(function (yes) {
      status(true);
      if (!yes) return later(EVERY);
      try {
        var at = position();
        sessionStorage.setItem(KEY, JSON.stringify({ x: window.scrollX, y: window.scrollY, q: query.value,
                                                     page: at.page, offset: at.offset }));
      } catch (e) {}
      location.reload();
    }, function () {
      status(false);
      later(SERVE ? 2000 : EVERY * 2);
    });
  }
  // a page in a hidden tab asks nothing of a web server, it asks once shown again
  if (!SERVE) document.addEventListener("visibilitychange", function () {
    if (document.hidden) { clearTimeout(timer); timer = null; } else if (!timer) later(0);
  });
  later(SERVE ? 700 : EVERY);
})();
