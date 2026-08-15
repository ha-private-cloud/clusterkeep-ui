(function () {
  "use strict";

  var STORAGE_KEY = "clusterkeep-theme";
  var root = document.documentElement;

  function stored() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      return null;
    }
  }

  function systemPrefersDark() {
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function apply(theme) {
    root.classList.remove("light", "dark");
    if (theme === "light" || theme === "dark") {
      root.classList.add(theme);
    }
  }

  function isDark() {
    var choice = stored();
    return choice ? choice === "dark" : systemPrefersDark();
  }

  apply(stored());

  document.addEventListener("DOMContentLoaded", function () {
    var button = document.querySelector("[data-theme-toggle]");
    if (!button) return;

    function sync() {
      var dark = isDark();
      button.setAttribute("aria-pressed", String(dark));
      button.setAttribute(
        "aria-label",
        dark ? "Switch to light theme" : "Switch to dark theme"
      );
    }

    button.hidden = false;
    sync();

    button.addEventListener("click", function () {
      var next = isDark() ? "light" : "dark";
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch (e) {}
      apply(next);
      sync();
    });

    window.matchMedia("(prefers-color-scheme: dark)").addEventListener(
      "change",
      function () {
        if (!stored()) sync();
      }
    );
  });
})();
