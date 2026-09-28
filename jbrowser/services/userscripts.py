"""User scripts (JavaScript) and user styles (CSS), scoped by domain pattern and space."""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineScript

from jbrowser.core.jsonstore import atomic_write_json, read_json

SCRIPT_PREFIX = "jb-user:"

RUN_AT = {
    "start": QWebEngineScript.InjectionPoint.DocumentCreation,
    "ready": QWebEngineScript.InjectionPoint.DocumentReady,
    "idle": QWebEngineScript.InjectionPoint.Deferred,
}


@dataclass
class UserScript:
    name: str
    kind: str = "js"                     # js | css
    code: str = ""
    matches: list[str] = field(default_factory=lambda: ["*"])  # "example.com", "*.example.com", "https://x/*"
    spaces: list[str] = field(default_factory=list)            # empty = all spaces
    run_at: str = "ready"
    enabled: bool = True
    all_frames: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    updated: float = field(default_factory=time.time)


def pattern_to_regex_source(pattern: str) -> str:
    """Translate a match pattern into a JS regex source string matched against location.href."""
    p = pattern.strip()
    if not p or p == "*":
        return ".*"
    if "://" not in p and "/" not in p:
        # Plain domain: matches the domain and its sub-domains on any scheme/path.
        host = p.lstrip("*.").replace(".", r"\.")
        return rf"^[a-z][a-z0-9+.\-]*://([^/]*\.)?{host}(:\d+)?(/.*)?$"
    out = []
    for ch in p:
        out.append(".*" if ch == "*" else "." if ch == "?" else re.escape(ch))
    return "^" + "".join(out) + "$"


class UserScriptService(QObject):
    changed = pyqtSignal()

    def __init__(self, path: Path, parent: QObject | None = None):
        super().__init__(parent)
        self._path = path
        self._items: list[UserScript] = []
        raw = read_json(path, [])
        for d in raw if isinstance(raw, list) else []:
            try:
                self._items.append(UserScript(**{k: v for k, v in d.items() if k in UserScript.__dataclass_fields__}))
            except TypeError:
                continue
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self.save_now)

    def save_now(self) -> None:
        self._timer.stop()
        atomic_write_json(self._path, [asdict(s) for s in self._items])

    def all(self) -> list[UserScript]:
        return list(self._items)

    def get(self, sid: str) -> UserScript | None:
        return next((s for s in self._items if s.id == sid), None)

    def upsert(self, script: UserScript) -> None:
        script.updated = time.time()
        for i, s in enumerate(self._items):
            if s.id == script.id:
                self._items[i] = script
                break
        else:
            self._items.append(script)
        self._timer.start()
        self.changed.emit()

    def remove(self, sid: str) -> None:
        self._items = [s for s in self._items if s.id != sid]
        self._timer.start()
        self.changed.emit()

    def for_space(self, space_id: str) -> list[UserScript]:
        return [s for s in self._items if s.enabled and (not s.spaces or space_id in s.spaces)]

    @staticmethod
    def _wrap(script: UserScript) -> str:
        regexes = json.dumps([pattern_to_regex_source(m) for m in (script.matches or ["*"])])
        guard = (f"var __jbRx={regexes}.map(function(s){{return new RegExp(s,'i');}});"
                 "if(!__jbRx.some(function(r){return r.test(location.href);}))return;")
        if script.kind == "css":
            css = json.dumps(script.code)
            body = ("var s=document.createElement('style');s.setAttribute('data-jbrowser-userstyle',"
                    f"{json.dumps(script.name)});s.textContent={css};"
                    "(document.head||document.documentElement).appendChild(s);")
            if script.run_at == "start":
                body = ("var add=function(){" + body + "};if(document.documentElement){add();}else{"
                        "new MutationObserver(function(m,o){if(document.documentElement){o.disconnect();add();}})"
                        ".observe(document,{childList:true});}")
            return f"(function(){{{guard}{body}}})();"
        return f"(function(){{{guard}\ntry{{\n{script.code}\n}}catch(e){{console.error('[JBrowser user script]',e);}}\n}})();"

    def sync_profile(self, profile: QWebEngineProfile, space_id: str) -> None:
        coll = profile.scripts()
        for existing in coll.toList():
            if existing.name().startswith(SCRIPT_PREFIX):
                coll.remove(existing)
        for s in self.for_space(space_id):
            ws = QWebEngineScript()
            ws.setName(SCRIPT_PREFIX + s.id)
            ws.setSourceCode(self._wrap(s))
            ws.setInjectionPoint(RUN_AT.get(s.run_at, QWebEngineScript.InjectionPoint.DocumentReady))
            ws.setRunsOnSubFrames(bool(s.all_frames))
            # JS runs in the page's world so it can use page globals; CSS only needs the DOM.
            ws.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld if s.kind == "js"
                          else QWebEngineScript.ScriptWorldId.UserWorld)
            coll.insert(ws)
