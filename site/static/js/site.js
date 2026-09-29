/* JBrowser website, every page: light/dark switch, copy buttons, and the newest release.
   Download links are built into each page when the site is generated; this script checks the
   GitHub API as well, so they point at a newer release as soon as it is published. */
(function () {
  "use strict";
  var root = document.documentElement;

  // ------------------------------------------------------------------ theme
  function setTheme(t) {
    root.setAttribute("data-theme", t);
    try { localStorage.setItem("jb-theme", t); } catch (e) {}
  }
  document.querySelectorAll(".theme-toggle").forEach(function (b) {
    b.addEventListener("click", function () {
      setTheme(root.getAttribute("data-theme") === "dark" ? "light" : "dark");
    });
  });
  try {
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function (e) {
      var saved = null;
      try { saved = localStorage.getItem("jb-theme"); } catch (err) {}
      if (!saved) root.setAttribute("data-theme", e.matches ? "dark" : "light");
    });
  } catch (e) {}

  // ------------------------------------------------------------------ copy buttons
  function copy(text, button) {
    var done = function () {
      var old = button.textContent;
      button.textContent = "Copied";
      button.classList.add("done");
      setTimeout(function () { button.textContent = old; button.classList.remove("done"); }, 1600);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, function () {});
  }
  document.querySelectorAll("[data-copy]").forEach(function (b) {
    b.addEventListener("click", function () { copy(b.getAttribute("data-copy"), b); });
  });
  window.JB = { copy: copy };

  // ------------------------------------------------------------------ install window
  // Download buttons open the install window: the one-line PowerShell install (copied when the visitor
  // clicks Download, and shown in full), with the installer file as the alternative. Links marked
  // data-direct download the file itself. Without JavaScript every button is a plain download link.
  var dialog = document.getElementById("install-dialog");
  var onWindows = /Windows/i.test(navigator.userAgent);
  document.querySelectorAll(".install-notwin").forEach(function (p) { p.hidden = onWindows; });
  if (dialog && typeof dialog.showModal === "function") {
    document.addEventListener("click", function (e) {
      var a = e.target.closest && e.target.closest("a[data-latest-exe]");
      if (!a || a.hasAttribute("data-direct") || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      var button = dialog.querySelector(".install-cmd .copy");
      var note = dialog.querySelector(".copied-note");
      if (note) note.hidden = true;
      if (button && navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(button.getAttribute("data-copy")).then(function () {
          if (note) note.hidden = false;
        }, function () {});
      }
      dialog.showModal();
    });
    dialog.addEventListener("click", function (e) { if (e.target === dialog) dialog.close(); });   // the backdrop
  }

  // ------------------------------------------------------------------ newest release
  var repo = (document.querySelector('meta[name="jb-repo"]') || {}).content;
  var baked = (document.querySelector('meta[name="jb-latest"]') || {}).content || "0.0.0";

  function newer(a, b) {
    var x = a.split("."), y = b.split(".");
    for (var i = 0; i < 3; i++) {
      var d = (parseInt(x[i], 10) || 0) - (parseInt(y[i], 10) || 0);
      if (d) return d > 0;
    }
    return false;
  }

  function fetchLatest() {
    var key = "jb-latest-release";
    try {
      var cached = JSON.parse(sessionStorage.getItem(key) || "null");
      if (cached && Date.now() - cached.at < 10 * 60 * 1000) return Promise.resolve(cached.info);
    } catch (e) {}
    return fetch("https://api.github.com/repos/" + repo + "/releases/latest", { headers: { Accept: "application/vnd.github+json" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (rel) {
        var info = null;
        (rel.assets || []).forEach(function (a) {
          var m = /^JBrowser-Setup-(\d+\.\d+\.\d+)\.exe$/i.exec(a.name);
          if (m) info = { version: m[1], url: a.browser_download_url, name: a.name, size: a.size, page: rel.html_url };
        });
        if (!info) throw new Error("no installer in the latest release");
        try { sessionStorage.setItem(key, JSON.stringify({ at: Date.now(), info: info })); } catch (e) {}
        return info;
      });
  }

  function apply(info) {
    if (!info || !newer(info.version, baked) && info.version !== baked) return info;
    document.querySelectorAll("[data-latest-exe]").forEach(function (a) { a.href = info.url; });
    document.querySelectorAll("[data-latest-release]").forEach(function (a) { a.href = info.page; });
    document.querySelectorAll("[data-latest-version]").forEach(function (e) { e.textContent = info.version; });
    document.querySelectorAll("[data-latest-name]").forEach(function (e) { e.textContent = info.name; });
    document.querySelectorAll("[data-latest-label]").forEach(function (e) {
      e.textContent = "Version " + info.version + (info.size ? " · " + Math.round(info.size / 1048576) + " MB" : "");
    });
    return info;
  }

  if (repo && document.querySelector("[data-latest-exe]")) {
    window.JB.latest = fetchLatest().then(apply);
    window.JB.latest.catch(function () {});   // offline or rate-limited: the built-in links stay
  }
})();
