/* JBrowser Source Docs: version switcher, search, "On this page" tracking, the mobile
   navigation and copy buttons on code blocks. */
(function () {
  "use strict";
  var body = document.body;
  var docsRoot = body.getAttribute("data-docs-root");        // relative path to docs/
  var version = body.getAttribute("data-version");           // "1.5.0" or "main"
  var versionDir = body.getAttribute("data-version-dir");    // "1.5.0", "latest" or "main"
  var page = body.getAttribute("data-page");                 // e.g. "engine/profiles.html"

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // ------------------------------------------------------------------ mobile navigation
  var menuBtn = document.querySelector(".menu-toggle");
  var scrim = document.querySelector(".sidebar-scrim");
  function setNav(open) {
    body.classList.toggle("nav-open", open);
    if (menuBtn) menuBtn.setAttribute("aria-expanded", String(open));
    if (scrim) scrim.hidden = !open;
  }
  if (menuBtn) menuBtn.addEventListener("click", function () { setNav(!body.classList.contains("nav-open")); });
  if (scrim) scrim.addEventListener("click", function () { setNav(false); });
  var active = document.querySelector(".sidebar a.active");
  if (active && active.scrollIntoView) active.scrollIntoView({ block: "center" });

  // ------------------------------------------------------------------ version switcher
  var vBtn = document.getElementById("version-btn");
  var vMenu = document.getElementById("version-menu");
  var manifest = null;

  function loadManifest() {
    if (!manifest) {
      manifest = fetch(docsRoot + "versions.json").then(function (r) { return r.json(); });
    }
    return manifest;
  }

  function targetFor(v) {
    return docsRoot + v.id + "/" + (v.pages.indexOf(page) >= 0 ? page : "index.html") + location.hash;
  }

  function buildMenu(data) {
    var list = vMenu.querySelector(".vm-list");
    list.innerHTML = data.versions.map(function (v) {
      var here = v.id === version;
      var has = v.pages.indexOf(page) >= 0;
      var tag = v.latest ? '<span class="vm-tag">latest</span>' : v.id === "main" ? '<span class="vm-tag dev">development</span>' : "";
      return '<li><a href="' + esc(targetFor(v)) + '"' + (here ? ' aria-current="true"' : "") + ">" +
        "<span>" + esc(v.id === "main" ? "main" : "v" + v.id) + "</span>" + tag +
        (has ? "" : '<span class="vm-missing">(no such page)</span>') +
        '<span class="vm-date">' + esc(v.date || "") + "</span></a></li>";
    }).join("");
  }

  function openMenu(open) {
    vMenu.hidden = !open;
    vBtn.setAttribute("aria-expanded", String(open));
    if (open) {
      loadManifest().then(function (data) {
        buildMenu(data);
        var cur = vMenu.querySelector('[aria-current="true"]') || vMenu.querySelector("a");
        if (cur) cur.focus();
      });
    }
  }
  if (vBtn && vMenu) {
    vBtn.addEventListener("click", function (e) { e.stopPropagation(); openMenu(vMenu.hidden); });
    document.addEventListener("click", function (e) { if (!vMenu.hidden && !vMenu.contains(e.target)) openMenu(false); });
    vMenu.addEventListener("keydown", function (e) {
      var links = Array.prototype.slice.call(vMenu.querySelectorAll("a"));
      var i = links.indexOf(document.activeElement);
      if (e.key === "Escape") { openMenu(false); vBtn.focus(); }
      else if (e.key === "ArrowDown") { e.preventDefault(); (links[i + 1] || links[0]).focus(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); (links[i - 1] || links[links.length - 1]).focus(); }
    });
  }
  // The "go to the latest documentation" banner keeps you on the same page when it exists there.
  var toLatest = document.querySelector(".to-latest");
  if (toLatest) {
    loadManifest().then(function (data) {
      var latest = data.versions.filter(function (v) { return v.latest; })[0];
      if (latest && latest.pages.indexOf(page) >= 0) toLatest.href = docsRoot + "latest/" + page;
    }).catch(function () {});
  }

  // ------------------------------------------------------------------ search
  var input = document.getElementById("search");
  var results = document.getElementById("search-results");
  var index = null, current = [], selected = -1;

  function loadIndex() {
    if (!index) {
      index = fetch(docsRoot + versionDir + "/search.json").then(function (r) { return r.json(); });
    }
    return index;
  }

  function score(entry, terms) {
    var t = entry.t.toLowerCase(), s = (entry.s || "").toLowerCase(), h = (entry.h || []).join(" ").toLowerCase();
    var b = (entry.b || "").toLowerCase(), total = 0;
    for (var i = 0; i < terms.length; i++) {
      var q = terms[i], sc = 0;
      if (t === q) sc += 30;
      if (t.indexOf(q) === 0) sc += 14;
      else if (t.indexOf(q) >= 0) sc += 9;
      if (h.indexOf(q) >= 0) sc += 5;
      if (s.indexOf(q) >= 0) sc += 2;
      if (b.indexOf(q) >= 0) sc += 1;
      if (!sc) return 0;              // every word must appear somewhere
      total += sc;
    }
    return total;
  }

  function snippet(text, terms) {
    if (!text) return "";
    var low = text.toLowerCase(), at = -1;
    for (var i = 0; i < terms.length && at < 0; i++) at = low.indexOf(terms[i]);
    var start = Math.max(0, at - 40);
    var out = esc((start ? "…" : "") + text.slice(start, start + 160));
    terms.forEach(function (q) {
      if (q.length > 1) out = out.replace(new RegExp("(" + q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig"), "<mark>$1</mark>");
    });
    return out;
  }

  function render(q) {
    var terms = q.toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) { results.hidden = true; return; }
    loadIndex().then(function (entries) {
      current = entries.map(function (e) { return { e: e, s: score(e, terms) }; })
        .filter(function (x) { return x.s > 0; })
        .sort(function (a, b) { return b.s - a.s; })
        .slice(0, 12);
      selected = current.length ? 0 : -1;
      results.innerHTML = current.length ? current.map(function (x, i) {
        return '<a href="' + esc(docsRoot + versionDir + "/" + x.e.u) + '"' + (i === 0 ? ' class="on"' : "") + ">" +
          '<span class="r-title">' + esc(x.e.t) + '</span><span class="r-section">' + esc(x.e.s || "") + "</span>" +
          '<span class="r-text">' + snippet(x.e.b, terms) + "</span></a>";
      }).join("") : '<p class="r-empty">Nothing found for “' + esc(q) + "”.</p>";
      results.hidden = false;
    });
  }

  function move(d) {
    var links = results.querySelectorAll("a");
    if (!links.length) return;
    selected = (selected + d + links.length) % links.length;
    links.forEach(function (a, i) { a.classList.toggle("on", i === selected); });
    links[selected].scrollIntoView({ block: "nearest" });
  }

  if (input && results) {
    input.addEventListener("focus", loadIndex);
    input.addEventListener("input", function () { render(input.value.trim()); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
      else if (e.key === "Enter") {
        var links = results.querySelectorAll("a");
        if (links[selected]) { e.preventDefault(); location.href = links[selected].href; }
      } else if (e.key === "Escape") { results.hidden = true; input.blur(); }
    });
    document.addEventListener("click", function (e) {
      if (!results.contains(e.target) && e.target !== input) results.hidden = true;
    });
    document.addEventListener("keydown", function (e) {
      var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
      if (!typing && (e.key === "/" || (e.key.toLowerCase() === "k" && (e.ctrlKey || e.metaKey)))) {
        e.preventDefault();
        input.focus();
        input.select();
      }
    });
  }

  // ------------------------------------------------------------------ "On this page"
  var tocLinks = {};
  document.querySelectorAll(".page-toc a").forEach(function (a) { tocLinks[decodeURIComponent(a.hash.slice(1))] = a; });
  var headings = Array.prototype.slice.call(document.querySelectorAll(".prose h2[id], .prose h3[id]"))
    .filter(function (h) { return tocLinks[h.id]; });
  if (headings.length && "IntersectionObserver" in window) {
    var visible = {};
    var mark = function () {
      var top = headings.filter(function (h) { return visible[h.id]; })[0];
      if (!top) return;
      Object.keys(tocLinks).forEach(function (id) { tocLinks[id].classList.toggle("on", id === top.id); });
    };
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { visible[e.target.id] = e.isIntersecting; });
      mark();
    }, { rootMargin: "-70px 0px -65% 0px" });
    headings.forEach(function (h) { io.observe(h); });
  }

  // ------------------------------------------------------------------ copy buttons on code
  document.querySelectorAll(".prose .highlight").forEach(function (block) {
    var pre = block.querySelector("pre");
    if (!pre) return;
    var b = document.createElement("button");
    b.type = "button";
    b.className = "code-copy-btn";
    b.textContent = "Copy";
    b.setAttribute("aria-label", "Copy this code");
    b.addEventListener("click", function () { window.JB && window.JB.copy(pre.innerText.replace(/\n$/, ""), b); });
    block.appendChild(b);
  });
})();
