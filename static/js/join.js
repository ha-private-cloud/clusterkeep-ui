(function () {
  "use strict";

  var form = document.getElementById("join-form");
  if (!form) return;

  form.addEventListener("submit", function () {
    var button = form.querySelector('button[type="submit"]');
    if (!button) return;
    button.disabled = true;
    button.textContent = "Creating account…";
  });
})();
