
// live reload, added only by uwiki serve: reloads after a rebuild, keeps scroll position and search
(function () {
  "use strict";
  var BUILD = "{build}";
  var KEY = "uwiki-reload";
  var query = document.getElementById("query");
  try {
    var saved = JSON.parse(sessionStorage.getItem(KEY) || "null");
    sessionStorage.removeItem(KEY);
    if (saved) {
      if (saved.q) {
        query.value = saved.q;
        query.dispatchEvent(new Event("input"));
      }
      requestAnimationFrame(function () { window.scrollTo(saved.x, saved.y); });
    }
  } catch (e) {}

  function check() {
    fetch("/__uwiki/build", { cache: "no-store" }).then(function (r) {
      return r.ok ? r.text() : BUILD;
    }).then(function (build) {
      if (build === BUILD) return setTimeout(check, 700);
      try {
        sessionStorage.setItem(KEY, JSON.stringify({ x: window.scrollX, y: window.scrollY, q: query.value }));
      } catch (e) {}
      location.reload();
    }, function () {
      setTimeout(check, 2000);
    });
  }
  setTimeout(check, 700);
})();
