(function () {
  function getParam(name) {
    var params = new URLSearchParams(window.location.search);
    return params.get(name);
  }

  var token = getParam("token");
  if (!token) {
    return;
  }

  var input = document.getElementById("token");
  if (input) {
    input.value = token;
  }
})();
