
// live reload, added only by uwiki serve: reloads after a rebuild, keeps scroll position and search;
// the position is the page at the top of the window and how far into it, as pages far from the window
// have sizes estimated till drawn
(function () {
  "use strict";
  var BUILD = "{build}";
  var KEY = "uwiki-reload";
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

  function check() {
    fetch("/__uwiki/build", { cache: "no-store" }).then(function (r) {
      return r.ok ? r.text() : BUILD;
    }).then(function (build) {
      if (build === BUILD) return setTimeout(check, 700);
      try {
        var at = position();
        sessionStorage.setItem(KEY, JSON.stringify({ x: window.scrollX, y: window.scrollY, q: query.value,
                                                     page: at.page, offset: at.offset }));
      } catch (e) {}
      location.reload();
    }, function () {
      setTimeout(check, 2000);
    });
  }
  setTimeout(check, 700);
})();
