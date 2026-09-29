"""JavaScript injected into pages. Kept in Python so the frozen build needs no data files."""
from __future__ import annotations

from PyQt6.QtCore import QFile, QIODevice

# World used for JBrowser's own scripts; page scripts can't see objects in this world.
BRIDGE_WORLD = 1  # QWebEngineScript.ScriptWorldId.ApplicationWorld

# --------------------------------------------------------------------------------------
# Smart-protection guard: tracks what makes a card unsafe to hibernate (playing media, unsaved
# form input, full screen). It runs in JBrowser's isolated world (BRIDGE_WORLD), so the page
# can neither see nor detect it: the DOM is shared between worlds, JavaScript objects are not.
# Open WebSockets and calls are detected outside the page (network requests and camera /
# microphone permissions, see TabController). Queried with window.__jbGuardProbe().
GUARD_JS = r"""
(function () {
  'use strict';
  if (window.__jbGuardProbe) return;
  var edited = new Set();
  document.addEventListener('input', function (e) {
    var t = e.target;
    if (t && (t.tagName === 'TEXTAREA' || t.tagName === 'INPUT' || t.isContentEditable)) edited.add(t);
  }, true);
  document.addEventListener('submit', function () { edited.clear(); }, true);
  window.__jbGuardProbe = function () {
    var media = false, dirty = false;
    try {
      document.querySelectorAll('video, audio').forEach(function (m) {
        if (!m.paused && !m.ended && m.readyState > 2) media = true;
      });
    } catch (e) {}
    edited.forEach(function (el) {
      if (!el.isConnected) { edited.delete(el); return; }
      var v = el.isContentEditable ? el.textContent : el.value;
      if (v && String(v).trim().length) dirty = true;
    });
    return JSON.stringify({ media: media, dirty: dirty, fullscreen: !!document.fullscreenElement });
  };
})();
"""

# --------------------------------------------------------------------------------------
# Main-world privacy signals: Global Privacy Control, Do Not Track, and canvas fingerprint noise.
# Bot checks (Google, Cloudflare) treat pages whose built-in functions were replaced as automated
# and answer with CAPTCHAs, so every replacement keeps the look of the original: same name and
# length, no prototype, and Function.prototype.toString reports "[native code]" as usual.
# CPU / memory / GPU values are left alone: faking them in the page but not in workers is itself
# a strong bot signal. Challenge and sign-in sites (EXEMPT) get none of this.
_PRIVACY_TEMPLATE = r"""
(function () {
  'use strict';
  var EXEMPT = __EXEMPT__, SEED = __SEED__, GPC = __GPC__, DNT = __DNT__, CANVAS = __CANVAS__;
  var host = location.hostname || '';
  if (EXEMPT.some(function (d) { return host === d || host.slice(-d.length - 1) === '.' + d; })
      || /(^|\.)google\.[a-z]{2,3}(\.[a-z]{2})?$/.test(host)) return;
  var FP = Function.prototype, nativeToString = FP.toString, masks = new WeakMap();
  function mask(fn, original) {
    masks.set(fn, nativeToString.call(original));
    try { Object.defineProperty(fn, 'length', { value: original.length }); } catch (e) {}
    return fn;
  }
  var shims = {
    toString() { return masks.has(this) ? masks.get(this) : nativeToString.call(this); }
  };
  masks.set(shims.toString, nativeToString.call(nativeToString));
  try { Object.defineProperty(FP, 'toString', { value: shims.toString, writable: true, configurable: true, enumerable: false }); } catch (e) {}
  function getter(proto, name, value) {
    var d = Object.getOwnPropertyDescriptor(proto, name);
    var g = Object.getOwnPropertyDescriptor({ get [name]() { return value; } }, name).get;
    if (d && d.get) mask(g, d.get);
    else masks.set(g, 'function get ' + name + '() { [native code] }');
    try { Object.defineProperty(proto, name, { get: g, set: undefined, configurable: true, enumerable: true }); } catch (e) {}
  }
  if (GPC) getter(Navigator.prototype, 'globalPrivacyControl', true);
  if (DNT) getter(Navigator.prototype, 'doNotTrack', '1');
  if (!CANVAS) return;
  // Per-site, per-session key: the same site sees stable values, different sites can't correlate.
  var key = SEED;
  for (var i = 0; i < host.length; i++) key = ((key << 5) - key + host.charCodeAt(i)) | 0;
  function noisy(data) {
    var k = key >>> 0;
    for (var p = 0; p < data.length; p += 4) {
      k = (k * 1664525 + 1013904223) >>> 0;
      if ((k & 0xff) < 6) { var c = (k >>> 8) % 3; data[p + c] = data[p + c] ^ 1; }
    }
  }
  try {
    var C2D = CanvasRenderingContext2D.prototype, HC = HTMLCanvasElement.prototype;
    var getImageData = C2D.getImageData, toDataURL = HC.toDataURL, toBlob = HC.toBlob;
    var noisyCopy = function (canvas) {
      if (!canvas.width || !canvas.height || canvas.width * canvas.height > 16777216) return canvas;
      var copy = document.createElement('canvas');
      copy.width = canvas.width; copy.height = canvas.height;
      var cx = copy.getContext('2d');
      cx.drawImage(canvas, 0, 0);
      var img = getImageData.call(cx, 0, 0, copy.width, copy.height);
      noisy(img.data);
      cx.putImageData(img, 0, 0);
      return copy;
    };
    var methods = {
      getImageData() { var img = getImageData.apply(this, arguments); try { noisy(img.data); } catch (e) {} return img; },
      toDataURL() { return toDataURL.apply(noisyCopy(this), arguments); },
      toBlob() { return toBlob.apply(noisyCopy(this), arguments); }
    };
    C2D.getImageData = mask(methods.getImageData, getImageData);
    HC.toDataURL = mask(methods.toDataURL, toDataURL);
    HC.toBlob = mask(methods.toBlob, toBlob);
  } catch (e) {}
})();
"""


def privacy_js(seed: int, exempt: list[str], gpc: bool, dnt: bool, canvas: bool) -> str:
    """The main-world privacy script, or "" when every part of it is switched off."""
    import json
    if not (gpc or dnt or canvas):
        return ""
    return (_PRIVACY_TEMPLATE.replace("__EXEMPT__", json.dumps(sorted(set(exempt))))
            .replace("__SEED__", str(int(seed) & 0x7FFFFFFF))
            .replace("__GPC__", "true" if gpc else "false").replace("__DNT__", "true" if dnt else "false")
            .replace("__CANVAS__", "true" if canvas else "false"))


# Element hiding (ad boxes, "Advertisement" frames). Runs in JBrowser's isolated world at document
# creation, picks the rules for its own site from DATA (FilterEngine.cosmetic_data) and adds them as
# one style sheet, as early as the page allows. ALLOW: sites where protection is switched off.
_COSMETIC_TEMPLATE = r"""
(function () {
  'use strict';
  var D = __DATA__, ALLOW = __ALLOW__;
  var h = (location.hostname || '').toLowerCase();
  if (!h || location.protocol.indexOf('http') !== 0) return;
  var parts = h.split('.'), chain = [];
  for (var i = 0; i < Math.max(1, parts.length - 1); i++) chain.push(parts.slice(i).join('.'));
  function hit(set) { for (var j = 0; j < chain.length; j++) if (set[chain[j]]) return true; return false; }
  if (hit(D.nc) || hit(ALLOW)) return;
  var unhide = {}, out = [];
  chain.forEach(function (c) { (D.u[c] || []).forEach(function (s) { unhide[s] = 1; }); });
  if (!hit(D.ng)) {
    D.g.forEach(function (s) {
      if (unhide[s]) return;
      var k = D.k[s];
      if (k && chain.some(function (c) { return k.indexOf(c) >= 0; })) return;
      out.push(s);
    });
  }
  chain.forEach(function (c) { (D.s[c] || []).forEach(function (s) { if (!unhide[s]) out.push(s); }); });
  if (!out.length) return;
  // One rule per selector: a selector this engine version doesn't understand only drops its own rule.
  var css = out.join('{display:none!important}\n') + '{display:none!important}';
  function add() {
    var root = document.documentElement;
    if (!root) return false;
    var st = document.createElement('style');
    st.textContent = css;
    root.appendChild(st);
    return true;
  }
  if (!add()) {
    var mo = new MutationObserver(function () { if (add()) mo.disconnect(); });
    mo.observe(document, { childList: true });
  }
})();
"""


def cosmetic_js(data: dict, allow: list[str]) -> str:
    import json
    return (_COSMETIC_TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
            .replace("__ALLOW__", json.dumps({d: 1 for d in allow})))

# --------------------------------------------------------------------------------------
# Password capture & autofill. Runs in an isolated world: the page cannot read the bridge,
# the fill function or any credential value before it is placed into the form.
AUTOFILL_JS = r"""
(function () {
  'use strict';
  if (window.__jbAutofill) return;
  window.__jbAutofill = true;
  if (typeof QWebChannel === 'undefined' || typeof qt === 'undefined' || !qt.webChannelTransport) return;
  var bridge = null, reported = -1, lastKey = '', lastAt = 0;

  function visible(el) {
    if (!el || el.disabled || el.readOnly) return false;
    var r = el.getBoundingClientRect(), st = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && st.visibility !== 'hidden' && st.display !== 'none';
  }
  function passwordFields() {
    return Array.prototype.filter.call(document.querySelectorAll('input[type=password]'), visible);
  }
  function usernameFor(pw) {
    var scope = pw.form || document;
    var inputs = Array.prototype.slice.call(scope.querySelectorAll('input'));
    for (var i = 0; i < inputs.length; i++) {
      var ac = (inputs[i].getAttribute('autocomplete') || '').toLowerCase();
      if ((ac.indexOf('username') >= 0 || ac === 'email') && visible(inputs[i])) return inputs[i];
    }
    var idx = inputs.indexOf(pw);
    for (var j = idx - 1; j >= 0; j--) {
      var t = (inputs[j].getAttribute('type') || 'text').toLowerCase();
      if ((t === 'text' || t === 'email' || t === 'tel') && visible(inputs[j])) return inputs[j];
    }
    return null;
  }
  function setValue(el, value) {
    var proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    el.focus();
    setter.call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }
  window.__jbFill = function (username, password) {
    var pws = passwordFields();
    if (!pws.length) return false;
    var pw = pws[0], user = usernameFor(pw);
    if (user && username) setValue(user, username);
    setValue(pw, password);
    return true;
  };
  function capture(form) {
    var scope = form && form.querySelectorAll ? form : document;
    var pws = Array.prototype.filter.call(scope.querySelectorAll('input[type=password]'),
                                          function (p) { return p.value; });
    if (!pws.length) return;
    var pw = pws[0];
    if (pws.length === 3) pw = pws[1];                              // old / new / confirm
    else if (pws.length === 2 && pws[0].value !== pws[1].value) pw = pws[1];
    var user = usernameFor(pw), uname = user ? user.value : '';
    var key = uname + '\u0000' + pw.value, now = Date.now();
    if (key === lastKey && now - lastAt < 3000) return;
    lastKey = key; lastAt = now;
    if (bridge) bridge.credentialsSubmitted(uname, pw.value);
  }
  document.addEventListener('submit', function (e) { capture(e.target); }, true);
  document.addEventListener('click', function (e) {
    var b = e.target && e.target.closest && e.target.closest('button, input[type=submit], [role=button]');
    if (!b) return;
    var form = b.form || b.closest('form');
    if (passwordFields().some(function (p) { return p.value; })) setTimeout(function () { capture(form); }, 0);
  }, true);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && e.target && e.target.type === 'password') capture(e.target.form);
  }, true);
  function report() {
    var n = passwordFields().length;
    if (n !== reported) { reported = n; if (bridge) bridge.loginFormDetected(n); }
  }
  // A video or sound in a format this engine can't decode (H.264, AAC: Qt WebEngine has no proprietary
  // codecs). Errors don't bubble, so listen in the capture phase; a failing <source> reports on itself.
  var mediaReported = false;
  document.addEventListener('error', function (e) {
    var t = e.target, m = t instanceof HTMLSourceElement ? t.parentElement : t;
    if (mediaReported || !(m instanceof HTMLMediaElement)) return;
    var unsupported = (m.error && m.error.code === 4) || (t !== m && m.networkState === 3);
    if (!unsupported) return;
    mediaReported = true;
    if (bridge) bridge.mediaUnsupported(m instanceof HTMLVideoElement ? 'video' : 'audio');
  }, true);
  new QWebChannel(qt.webChannelTransport, function (ch) { bridge = ch.objects.jbBridge; reported = -1; report(); });
  var timer = 0;
  new MutationObserver(function () { clearTimeout(timer); timer = setTimeout(report, 450); })
    .observe(document.documentElement, { childList: true, subtree: true, attributes: true,
                                         attributeFilter: ['type', 'style', 'class', 'hidden'] });
})();
"""

INTERSTITIAL_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Dangerous site blocked</title>
<style>
  html,body{height:100%;margin:0;background:#3b0d12;color:#fff;font-family:'Segoe UI',sans-serif}
  .wrap{max-width:640px;margin:0 auto;padding:12vh 32px}
  .icon{font-size:56px;line-height:1}
  h1{font-weight:600;font-size:28px;margin:18px 0 10px}
  p{font-size:15px;line-height:1.6;color:#f3d6d9}
  code{background:rgba(255,255,255,.12);padding:2px 6px;border-radius:5px;color:#fff}
  .hint{margin-top:28px;font-size:13px;color:#e0aab1}
</style></head><body><div class="wrap">
<div class="icon">&#9888;</div>
<h1>This site has been reported as dangerous</h1>
<p>JBrowser stopped <code>__HOST__</code> from loading because it appears on a public list of
__KIND__ sites. Pages like this can steal passwords, payment details or install harmful software.</p>
<p>Use the bar at the top of this card to go back to safety. You can continue to the site if you are sure
it is safe, but only do so if you trust it completely.</p>
<p class="hint">Lists used: URLhaus (malware) and Phishing Army (phishing). Checks happen on this device.</p>
</div></body></html>"""


CLEAR_SITE_STORAGE_JS = r"""
(async function () {
  try { localStorage.clear(); } catch (e) {}
  try { sessionStorage.clear(); } catch (e) {}
  try {
    if (indexedDB.databases) (await indexedDB.databases()).forEach(function (d) { indexedDB.deleteDatabase(d.name); });
  } catch (e) {}
  try { (await caches.keys()).forEach(function (k) { caches.delete(k); }); } catch (e) {}
  try {
    (await navigator.serviceWorker.getRegistrations()).forEach(function (r) { r.unregister(); });
  } catch (e) {}
})();
"""

_qwebchannel_cache: str | None = None


def qwebchannel_js() -> str:
    """qwebchannel.js ships as a Qt resource inside the QtWebChannel module."""
    global _qwebchannel_cache
    if _qwebchannel_cache is None:
        import PyQt6.QtWebChannel as _wc  # loading the module registers the resource
        assert _wc

        f = QFile(":/qtwebchannel/qwebchannel.js")
        if f.open(QIODevice.OpenModeFlag.ReadOnly):
            _qwebchannel_cache = bytes(f.readAll()).decode("utf-8")
            f.close()
        else:
            _qwebchannel_cache = ""
    return _qwebchannel_cache
