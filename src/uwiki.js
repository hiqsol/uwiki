window.onload = function(event) {
  var hs = document.querySelectorAll("h2, h3, h4, h5, h6");
  console.log(hs);
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
      console.log('==', h.tagName, h.id);
      li = document.createElement("li");
      var a = document.createElement("a");
      a.href = "#" + h.id;
      a.textContent = h.textContent.split(' / ').pop();
      li.appendChild(a);
      parent.appendChild(li);
      i++;
    } else if (h.tagName[1] > first.tagName[1]) {
      console.log('> ', h.tagName, h.id);
      var ul = document.createElement("ul");
      li.appendChild(ul);
      i = processHeaders(ul, headers, i);
    } else {
      return i;
    }
  }
  return i;
}
