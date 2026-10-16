window.onload = function(event) {
  var hs = document.querySelectorAll("h2.page, h3.page, h4.page, h5.page, h6.page");
  var toc = document.getElementById("toc");
  processHeaders(toc, hs, 0);
};

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
      a.textContent = h.textContent.split(' / ').pop();
      li.appendChild(a);
      parent.appendChild(li);
      i++;
    } else if (h.tagName[1] > first.tagName[1]) {
      var ul = document.createElement("ul");
      li.appendChild(ul);
      i = processHeaders(ul, headers, i);
    } else {
      return i;
    }
  }
  return i;
}
