(function () {
  "use strict";

  var button = document.querySelector("[data-nav-toggle]");
  var nav = document.getElementById("nav-links");
  if (!button || !nav) return;

  function isOpen() {
    return !nav.classList.contains("hidden");
  }

  function setOpen(open) {
    nav.classList.toggle("hidden", !open);
    nav.classList.toggle("flex", open);
    button.setAttribute("aria-expanded", String(open));
  }

  button.addEventListener("click", function () {
    setOpen(!isOpen());
  });
})();
