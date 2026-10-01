/* JBrowser home page: scroll reveals, the hero tilt, theme-aware screenshots, the feature tour,
   the colour-tint picker (real screenshots) and a lightbox for every screenshot. */
(function () {
  "use strict";
  var root = document.documentElement;
  var base = (function () {
    var img = document.querySelector('img.shot[src*="static/img/shots/"]');
    return img ? img.getAttribute("src").split("static/img/shots/")[0] + "static/img/shots/" : "static/img/shots/";
  })();
  var reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

  function theme() { return root.getAttribute("data-theme") === "light" ? "light" : "dark"; }
  function srcset(name, widths, fullWidth) {
    return widths.map(function (w) {
      return base + name + "-" + w + ".webp " + (w === "full" ? (fullWidth || 2595) + "w" : w + "w");
    }).join(", ");
  }
  function setShot(img, name, widths) {
    img.srcset = srcset(name, widths);
    img.src = base + name + "-1920.webp";
    img.setAttribute("data-full", base + name + "-" + (widths.indexOf("full") >= 0 ? "full" : "1920") + ".webp");
  }
  var SHOWCASE = [1280, 1920, "full"];

  // ------------------------------------------------------------ reveal on scroll
  var reveals = Array.prototype.slice.call(document.querySelectorAll(".reveal"));
  // Once revealed, an element drops the reveal transition so its own hover effects are quick again.
  function settle(el) {
    el.addEventListener("transitionend", function done(e) {
      if (e.target !== el || e.propertyName !== "opacity") return;
      el.removeEventListener("transitionend", done);
      el.classList.remove("reveal");
      el.style.transitionDelay = "";
    });
  }
  if ("IntersectionObserver" in window && !reduced) {
    root.classList.add("js-reveal");
    // Safety net: whatever is on screen but still hidden after 3 s (a tab that was in the background)
    // simply appears; things further down keep their animation.
    var sweep = function () {
      reveals.forEach(function (el) { if (el.getBoundingClientRect().top < innerHeight) el.classList.add("in"); });
    };
    setTimeout(sweep, 3000);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) setTimeout(sweep, 400); });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
    }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    var heroIndex = 0;
    reveals.forEach(function (el) {
      var delay = 0;
      if (el.closest(".hero")) {
        delay = heroIndex++ * 90;
      } else {
        // neighbours in a grid or list follow one another
        var siblings = Array.prototype.filter.call(el.parentElement.children, function (c) { return c.classList.contains("reveal"); });
        if (siblings.length > 1) delay = siblings.indexOf(el) * 85;
      }
      el.style.transitionDelay = delay + "ms";
      settle(el);
    });
    reveals.forEach(function (el) { io.observe(el); });
  } else {
    reveals.forEach(function (el) { el.classList.add("in"); });
  }

  // ------------------------------------------------------------ gentle parallax on the big pictures
  var drifting = Array.prototype.slice.call(document.querySelectorAll("[data-parallax]"));
  if (drifting.length && !reduced) {
    var queued = false;
    var drift = function () {
      queued = false;
      drifting.forEach(function (el) {
        var r = el.getBoundingClientRect();
        if (r.bottom < -100 || r.top > innerHeight + 100) return;
        var k = (r.top + r.height / 2 - innerHeight / 2) / innerHeight;      // -0.5 … 0.5 while on screen
        el.style.setProperty("--py", (-k * parseFloat(el.getAttribute("data-parallax") || "16")).toFixed(1) + "px");
      });
    };
    addEventListener("scroll", function () { if (!queued) { queued = true; requestAnimationFrame(drift); } }, { passive: true });
    addEventListener("resize", drift, { passive: true });
    drift();
  }

  // ------------------------------------------------------------ hero tilt: flattens as you scroll
  var hero = document.querySelector(".hero-shot");
  if (hero && !reduced) {
    var ticking = false;
    var update = function () {
      ticking = false;
      var r = hero.getBoundingClientRect();
      var k = Math.min(1, Math.max(0, (innerHeight - r.top) / (innerHeight * 0.9)));
      hero.style.setProperty("--tilt", (14 * (1 - k)).toFixed(2) + "deg");
      hero.style.setProperty("--zoom", (0.94 + 0.06 * k).toFixed(3));
    };
    addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
    update();
  }

  // ------------------------------------------------------------ light / dark screenshots
  function applyTheme() {
    document.querySelectorAll("img[data-themed]").forEach(function (img) {
      setShot(img, img.getAttribute("data-themed") + "-" + theme(), SHOWCASE);
    });
    if (current && current.hasAttribute("data-themed")) show(current, false);
  }
  new MutationObserver(applyTheme).observe(root, { attributes: true, attributeFilter: ["data-theme"] });

  // ------------------------------------------------------------ the tour
  var tabs = Array.prototype.slice.call(document.querySelectorAll(".tour-tabs [role=tab]"));
  var panel = document.getElementById("tour-panel");
  var tourImg = document.getElementById("tour-img");
  var tourSection = document.querySelector(".tour");
  var current = tabs[0] || null, timer = null, TOUR_MS = 7000, visible = false, hovering = false;

  function shotName(tab) {
    return tab.hasAttribute("data-themed") ? tab.getAttribute("data-themed") + "-" + theme() : tab.getAttribute("data-shot");
  }
  function show(tab, animate) {
    current = tab;
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
      if (on) { var bar = t.querySelector(".tt-bar"); if (bar) { bar.style.animation = "none"; void bar.offsetWidth; bar.style.animation = ""; } }
    });
    panel.setAttribute("aria-labelledby", tab.id);
    var apply = function () {
      document.getElementById("tour-title").textContent = tab.getAttribute("data-title");
      document.getElementById("tour-text").textContent = tab.getAttribute("data-text");
      document.getElementById("tour-chips").innerHTML = tab.getAttribute("data-chips").split("|")
        .map(function (c) { var li = document.createElement("li"); li.textContent = c; return li.outerHTML; }).join("");
      tourImg.alt = tab.getAttribute("data-alt");
      setShot(tourImg, shotName(tab), SHOWCASE);
      var done = function () { panel.classList.remove("swap"); };
      if (tourImg.complete) requestAnimationFrame(done); else tourImg.onload = done;
    };
    if (animate && !reduced) { panel.classList.add("swap"); setTimeout(apply, 220); } else { apply(); }
    // preload the next one so the switch is instant
    var next = tabs[(tabs.indexOf(tab) + 1) % tabs.length];
    if (next) { var pre = new Image(); pre.srcset = srcset(shotName(next), SHOWCASE); pre.sizes = tourImg.sizes; }
  }
  function schedule() {
    clearTimeout(timer);
    var paused = !visible || hovering || reduced;
    if (tourSection) tourSection.classList.toggle("paused", paused);
    if (!paused) timer = setTimeout(function () { show(tabs[(tabs.indexOf(current) + 1) % tabs.length], true); schedule(); }, TOUR_MS);
  }
  if (tabs.length) {
    if (tourSection) tourSection.style.setProperty("--tour-ms", TOUR_MS + "ms");
    tabs.forEach(function (tab, i) {
      tab.addEventListener("click", function () { if (tab !== current) show(tab, true); schedule(); });
      tab.addEventListener("keydown", function (e) {
        var d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
        if (e.key === "Home") d = -i; else if (e.key === "End") d = tabs.length - 1 - i;
        if (!d) return;
        e.preventDefault();
        var t = tabs[(i + d + tabs.length) % tabs.length];
        t.focus(); show(t, true); schedule();
      });
    });
    [panel, document.querySelector(".tour-tabs")].forEach(function (el) {
      el.addEventListener("mouseenter", function () { hovering = true; schedule(); });
      el.addEventListener("mouseleave", function () { hovering = false; schedule(); });
      el.addEventListener("focusin", function () { hovering = true; schedule(); });
      el.addEventListener("focusout", function () { hovering = false; schedule(); });
    });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) { visible = entries[0].isIntersecting; schedule(); }, { threshold: 0.35 })
        .observe(tourSection);
    }
  }

  // ------------------------------------------------------------ colour tints
  var swatches = Array.prototype.slice.call(document.querySelectorAll(".swatches .sw"));
  var tintImg = document.getElementById("tint-img");
  var tintBox = document.querySelector(".colours-shot");
  function pick(sw, focus) {
    swatches.forEach(function (s) { s.setAttribute("aria-checked", String(s === sw)); s.tabIndex = s === sw ? 0 : -1; });
    var key = sw.getAttribute("data-tint");
    var name = sw.getAttribute("title");
    document.getElementById("tint-name").textContent = name;
    var loader = new Image();
    loader.sizes = tintImg.sizes;
    loader.srcset = srcset("tint-" + key, [1280, "full"], 1640);
    tintBox.classList.add("loading");
    loader.onload = loader.onerror = function () {
      tintImg.srcset = loader.srcset;
      tintImg.src = base + "tint-" + key + "-1280.webp";
      tintImg.alt = "The corner of the JBrowser window with the " + name.toLowerCase() + " colour tint";
      tintBox.classList.remove("loading");
    };
    if (focus) sw.focus();
  }
  swatches.forEach(function (sw, i) {
    sw.tabIndex = sw.getAttribute("aria-checked") === "true" ? 0 : -1;
    sw.addEventListener("click", function () { pick(sw, false); });
    sw.addEventListener("keydown", function (e) {
      var d = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
      if (!d) return;
      e.preventDefault();
      pick(swatches[(i + d + swatches.length) % swatches.length], true);
    });
    // warm the cache when the pointer comes near
    sw.addEventListener("mouseenter", function () { var p = new Image(); p.sizes = tintImg.sizes; p.srcset = srcset("tint-" + sw.getAttribute("data-tint"), [1280, "full"], 1640); }, { once: true });
  });

  // ------------------------------------------------------------ lightbox
  var box = document.getElementById("lightbox");
  var boxImg = document.getElementById("lightbox-img");
  document.querySelectorAll("[data-zoom]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var img = btn.querySelector("img");
      if (!box || typeof box.showModal !== "function") { window.open(img.currentSrc || img.src); return; }
      boxImg.src = img.getAttribute("data-full") || img.currentSrc || img.src;
      boxImg.alt = img.alt;
      box.showModal();
    });
  });
  if (box) box.addEventListener("click", function (e) { if (e.target === box) box.close(); });

  // the screenshots follow the theme from the start (dark is in the HTML)
  if (theme() === "light") applyTheme();
  document.querySelectorAll("img.shot").forEach(function (img) {
    if (!img.hasAttribute("data-full")) {
      var m = /shots\/([a-z\-]+)-(1280|1920)\.webp/.exec(img.getAttribute("src") || "");
      if (m) img.setAttribute("data-full", base + m[1] + "-full" + ".webp");
    }
  });
  if (current) schedule();
})();
