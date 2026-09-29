/* JBrowser home page: the colour-tint picker on the window mock-up, and illustrations that
   animate in when they scroll into view. */
(function () {
  "use strict";
  var mock = document.getElementById("mock");
  var swatches = Array.prototype.slice.call(document.querySelectorAll(".tints .sw"));

  function choose(sw, focus) {
    swatches.forEach(function (s) { s.setAttribute("aria-checked", String(s === sw)); s.tabIndex = s === sw ? 0 : -1; });
    if (mock) mock.style.setProperty("--tint", sw.getAttribute("data-tint"));
    if (focus) sw.focus();
  }
  swatches.forEach(function (sw, i) {
    sw.tabIndex = sw.getAttribute("aria-checked") === "true" ? 0 : -1;
    sw.addEventListener("click", function () { choose(sw, false); });
    sw.addEventListener("keydown", function (e) {
      var d = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
      if (!d) return;
      e.preventDefault();
      choose(swatches[(i + d + swatches.length) % swatches.length], true);
    });
  });

  var demos = document.querySelectorAll(".gallery-demo");
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { threshold: 0.35 });
    demos.forEach(function (d) { io.observe(d); });
  } else {
    demos.forEach(function (d) { d.classList.add("in"); });
  }
})();
