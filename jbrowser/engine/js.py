"""JavaScript injected into pages. Kept in Python so the frozen build needs no data files."""
from __future__ import annotations

from PyQt6.QtCore import QFile, QIODevice

# World used for JBrowser's own scripts; page scripts can't see objects in this world.
BRIDGE_WORLD = 1  # QWebEngineScript.ScriptWorldId.ApplicationWorld

# --------------------------------------------------------------------------------------
# Smart-protection guard (main world, document creation). Tracks the things that make a
# card unsafe to hibernate: playing media, open WebSockets / WebRTC calls, unsaved edits
# and beforeunload handlers. Queried by the lifecycle manager via window.__jbGuardProbe().
GUARD_JS = r"""
(function () {
  'use strict';
  if (window.__jbGuardProbe) return;
  var sockets = new Set(), peers = new Set(), edited = new Set(), beforeUnload = 0;
  try {
    var NativeWS = window.WebSocket;
    if (NativeWS) {
      var JBWebSocket = function WebSocket(url, protocols) {
        var ws = arguments.length > 1 ? new NativeWS(url, protocols) : new NativeWS(url);
        sockets.add(ws);
        ws.addEventListener('close', function () { sockets.delete(ws); });
        return ws;
      };
      JBWebSocket.prototype = NativeWS.prototype;
      ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'].forEach(function (k) { JBWebSocket[k] = NativeWS[k]; });
      window.WebSocket = JBWebSocket;
    }
  } catch (e) {}
  try {
    var NativePC = window.RTCPeerConnection;
    if (NativePC) {
      var JBPC = function RTCPeerConnection(a, b) {
        var pc = arguments.length > 1 ? new NativePC(a, b) : new NativePC(a);
        peers.add(pc);
        return pc;
      };
      JBPC.prototype = NativePC.prototype;
      if (NativePC.generateCertificate) JBPC.generateCertificate = NativePC.generateCertificate.bind(NativePC);
      window.RTCPeerConnection = JBPC;
      if (window.webkitRTCPeerConnection) window.webkitRTCPeerConnection = JBPC;
    }
  } catch (e) {}
  try {
    var nativeAdd = window.addEventListener, nativeRemove = window.removeEventListener;
    window.addEventListener = function (type, fn, opts) {
      if (type === 'beforeunload' && fn) beforeUnload++;
      return nativeAdd.call(this, type, fn, opts);
    };
    window.removeEventListener = function (type, fn, opts) {
      if (type === 'beforeunload' && fn && beforeUnload > 0) beforeUnload--;
      return nativeRemove.call(this, type, fn, opts);
    };
  } catch (e) {}
  document.addEventListener('input', function (e) {
    var t = e.target;
    if (t && (t.tagName === 'TEXTAREA' || t.tagName === 'INPUT' || t.isContentEditable)) edited.add(t);
  }, true);
  document.addEventListener('submit', function () { edited.clear(); }, true);
  Object.defineProperty(window, '__jbGuardProbe', {
    value: function () {
      var media = false, ws = 0, rtc = 0, dirty = false;
      try {
        document.querySelectorAll('video, audio').forEach(function (m) {
          if (!m.paused && !m.ended && m.readyState > 2) media = true;
        });
      } catch (e) {}
      sockets.forEach(function (s) { if (s.readyState <= 1) ws++; else sockets.delete(s); });
      peers.forEach(function (p) {
        if (p.connectionState !== 'closed' && p.signalingState !== 'closed') rtc++; else peers.delete(p);
      });
      edited.forEach(function (el) {
        if (!el.isConnected) { edited.delete(el); return; }
        var v = el.isContentEditable ? el.textContent : el.value;
        if (v && String(v).trim().length) dirty = true;
      });
      var unload = beforeUnload > 0 || typeof window.onbeforeunload === 'function';
      return JSON.stringify({ media: media, ws: ws, rtc: rtc, dirty: dirty, beforeunload: unload,
                              fullscreen: !!document.fullscreenElement });
    }
  });
})();
"""

GPC_JS = r"""
(function () {
  try {
    Object.defineProperty(Navigator.prototype, 'globalPrivacyControl',
      { get: function () { return true; }, configurable: true, enumerable: true });
  } catch (e) {}
})();
"""

DNT_JS = r"""
(function () {
  try {
    Object.defineProperty(Navigator.prototype, 'doNotTrack',
      { get: function () { return '1'; }, configurable: true, enumerable: true });
  } catch (e) {}
})();
"""

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
  new QWebChannel(qt.webChannelTransport, function (ch) { bridge = ch.objects.jbBridge; reported = -1; report(); });
  var timer = 0;
  new MutationObserver(function () { clearTimeout(timer); timer = setTimeout(report, 450); })
    .observe(document.documentElement, { childList: true, subtree: true, attributes: true,
                                         attributeFilter: ['type', 'style', 'class', 'hidden'] });
})();
"""

_FINGERPRINT_TEMPLATE = r"""
(function () {
  'use strict';
  var EXEMPT = __EXEMPT__, SEED = __SEED__;
  var host = location.hostname || '';
  if (EXEMPT.some(function (d) { return host === d || host.slice(-d.length - 1) === '.' + d; })) return;
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
    var C2D = CanvasRenderingContext2D.prototype, getImageData = C2D.getImageData;
    C2D.getImageData = function () {
      var img = getImageData.apply(this, arguments);
      try { noisy(img.data); } catch (e) {}
      return img;
    };
    var HC = HTMLCanvasElement.prototype, toDataURL = HC.toDataURL, toBlob = HC.toBlob;
    function noisyCopy(canvas) {
      if (!canvas.width || !canvas.height || canvas.width * canvas.height > 16777216) return canvas;
      var copy = document.createElement('canvas');
      copy.width = canvas.width; copy.height = canvas.height;
      var cx = copy.getContext('2d');
      cx.drawImage(canvas, 0, 0);
      var img = getImageData.call(cx, 0, 0, copy.width, copy.height);
      noisy(img.data);
      cx.putImageData(img, 0, 0);
      return copy;
    }
    HC.toDataURL = function () { return toDataURL.apply(noisyCopy(this), arguments); };
    HC.toBlob = function () { return toBlob.apply(noisyCopy(this), arguments); };
  } catch (e) {}
  try {
    Object.defineProperty(Navigator.prototype, 'hardwareConcurrency', { get: function () { return 4; }, configurable: true });
    Object.defineProperty(Navigator.prototype, 'deviceMemory', { get: function () { return 8; }, configurable: true });
  } catch (e) {}
  function patchGL(proto) {
    if (!proto) return;
    var getParameter = proto.getParameter;
    proto.getParameter = function (p) {
      if (p === 0x9245) return 'Google Inc.';                 // UNMASKED_VENDOR_WEBGL
      if (p === 0x9246) return 'ANGLE (Generic Renderer)';    // UNMASKED_RENDERER_WEBGL
      return getParameter.apply(this, arguments);
    };
  }
  try { patchGL(window.WebGLRenderingContext && WebGLRenderingContext.prototype); } catch (e) {}
  try { patchGL(window.WebGL2RenderingContext && WebGL2RenderingContext.prototype); } catch (e) {}
})();
"""


def fingerprint_js(seed: int, exempt: list[str]) -> str:
    import json
    return _FINGERPRINT_TEMPLATE.replace("__EXEMPT__", json.dumps(sorted(set(exempt)))) \
        .replace("__SEED__", str(int(seed) & 0x7FFFFFFF))


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
