window.onload = function(event) {
  var hs = document.querySelectorAll("h2, h3, h4, h5, h6");
  var toc = document.getElementById("toc");
  for (var i = 0; i < hs.length; i++) {
    var h = hs[i];
    if (!h.id) {
      continue;
    }
    var ul = document.createElement("ul");
    ul.id = "toc." + h.id;
    var a = document.createElement("a");
    a.href = "#" + h.id;
    a.textContent = h.id;
    var li = document.createElement("li");
    li.appendChild(a);
    toc.appendChild(li);
  }
};

