(function () {
  var year = new Date().getFullYear();
  var node = document.getElementById("year");
  if (node) {
    node.textContent = year;
  }
})();
