"""Encrypted local password vault.

* Entries are serialised to JSON and sealed with AES-256-GCM using a random 256-bit key.
* The vault key is protected either by Windows DPAPI (default — bound to the Windows
  user account, transparent unlock) or by a master password (Scrypt KDF, n=2^17).
* Nothing sensitive is ever written to disk in plaintext.
"""
from __future__ import annotations

import base64
import csv
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal

from jbrowser.core.jsonstore import atomic_write_bytes
from jbrowser.core.urls import origin_of, strip_www
from jbrowser.platform import win

log = logging.getLogger(__name__)

_AAD_DATA = b"jbrowser-vault-data-v1"
_AAD_KEY = b"jbrowser-vault-key-v1"
# OWASP's recommended Scrypt cost (about 0.2 s and 128 MB per unlock). Each vault stores the parameters
# it was sealed with, so vaults made with the older n=2^15 still open and move up when the password is set.
_SCRYPT = {"n": 2 ** 17, "r": 8, "p": 1}


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


@dataclass
class Credential:
    origin: str
    username: str
    password: str
    space_id: str = ""                 # "" = available in every space
    note: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    last_used: float = 0.0

    @property
    def host(self) -> str:
        return strip_www(QUrl(self.origin).host())


# The most common leaked passwords (and obvious keyboard walks); a password on this list
# is weak whatever its length.
_COMMON = {
    "password", "password1", "password123", "passw0rd", "p@ssw0rd", "123456", "1234567", "12345678",
    "123456789", "1234567890", "12345", "111111", "000000", "123123", "654321", "qwerty", "qwerty123",
    "qwertyuiop", "asdfgh", "asdfghjkl", "zxcvbnm", "1q2w3e4r", "1qaz2wsx", "abc123", "iloveyou",
    "letmein", "welcome", "welcome1", "admin", "admin123", "monkey", "dragon", "football", "baseball",
    "sunshine", "princess", "master", "shadow", "superman", "trustno1", "starwars", "whatever",
    "michael", "jennifer", "charlie", "hello123", "freedom", "login", "changeme", "secret",
}


def password_problems(entries: list[Credential]) -> dict[str, list[str]]:
    """Map credential id to a list of problems ("weak", "reused"); healthy logins are omitted.

    Everything is computed locally from the decrypted vault; nothing leaves the machine."""
    hosts_by_password: dict[str, set[str]] = {}
    for c in entries:
        if c.password:
            hosts_by_password.setdefault(c.password, set()).add(c.host)
    out: dict[str, list[str]] = {}
    for c in entries:
        pw = c.password
        if not pw:
            continue
        problems = []
        classes = sum((any(ch.islower() for ch in pw), any(ch.isupper() for ch in pw),
                       any(ch.isdigit() for ch in pw), any(not ch.isalnum() for ch in pw)))
        if (len(pw) < 8 or pw.lower() in _COMMON or len(set(pw)) <= 3
                or (len(pw) < 12 and classes <= 1)):
            problems.append("weak")
        if len(hosts_by_password.get(pw, ())) > 1:
            problems.append("reused")
        if problems:
            out[c.id] = problems
    return out


class VaultError(Exception):
    pass


class PasswordVault(QObject):
    changed = pyqtSignal()
    lockChanged = pyqtSignal(bool)  # True when locked

    AUTO_LOCK_MS = 30 * 60 * 1000

    def __init__(self, path: Path, parent: QObject | None = None):
        super().__init__(parent)
        self._path = path
        self._key: bytes | None = None
        self._entries: list[Credential] = []
        self._never: list[str] = []
        self._header: dict = {}
        if path.exists():
            try:
                self._header = json.loads(path.read_bytes().decode("utf-8"))
            except (OSError, ValueError) as exc:
                log.error("Vault header unreadable: %s", exc)
                self._header = {}
        if not self._header:
            self._header = {"v": 1, "mode": "dpapi" if win.IS_WINDOWS else "master"}
        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.setInterval(self.AUTO_LOCK_MS)
        self._idle.timeout.connect(self._auto_lock)

    # ------------------------------------------------------------ lock state
    @property
    def mode(self) -> str:
        return self._header.get("mode", "dpapi")

    @property
    def is_locked(self) -> bool:
        return self._key is None

    @property
    def exists(self) -> bool:
        return self._path.exists()

    def _auto_lock(self) -> None:
        if self.mode == "master":
            self.lock()

    def _poke(self) -> None:
        if self.mode == "master":
            self._idle.start()

    def ensure_unlocked(self) -> bool:
        """Unlock transparently when protected by DPAPI. Master-password vaults need unlock()."""
        if self._key is not None:
            self._poke()
            return True
        if self.mode == "dpapi":
            return self.unlock()
        return False

    def unlock(self, password: str | None = None) -> bool:
        if self._key is not None:
            return True
        h = self._header
        try:
            if "wrapped_key" not in h:          # brand-new vault
                if self.mode == "master" and not password:
                    return False
                self._key = AESGCM.generate_key(bit_length=256)
                if self.mode == "master":
                    self._wrap_with_password(password or "")
                else:
                    h["wrapped_key"] = _b64(win.dpapi_protect(self._key))
                self._entries, self._never = [], []
                self._save()
            elif self.mode == "dpapi":
                self._key = win.dpapi_unprotect(_unb64(h["wrapped_key"]))
                self._load_entries()
            else:
                if not password:
                    return False
                kek = Scrypt(salt=_unb64(h["salt"]), length=32, **h.get("kdf", _SCRYPT)).derive(
                    password.encode("utf-8"))
                self._key = AESGCM(kek).decrypt(_unb64(h["key_nonce"]), _unb64(h["wrapped_key"]), _AAD_KEY)
                self._load_entries()
        except (InvalidTag, OSError, KeyError, ValueError) as exc:
            log.info("Vault unlock failed: %s", exc)
            self._key = None
            return False
        self._poke()
        self.lockChanged.emit(False)
        self.changed.emit()
        return True

    def lock(self) -> None:
        if self._key is None:
            return
        self._key = None
        self._entries = []
        self._never = []
        self.lockChanged.emit(True)
        self.changed.emit()

    def verify_password(self, password: str) -> bool:
        h = self._header
        if self.mode != "master":
            return True
        try:
            kek = Scrypt(salt=_unb64(h["salt"]), length=32, **h.get("kdf", _SCRYPT)).derive(password.encode("utf-8"))
            AESGCM(kek).decrypt(_unb64(h["key_nonce"]), _unb64(h["wrapped_key"]), _AAD_KEY)
            return True
        except (InvalidTag, KeyError, ValueError):
            return False

    def _wrap_with_password(self, password: str) -> None:
        assert self._key is not None
        salt = os.urandom(16)
        kek = Scrypt(salt=salt, length=32, **_SCRYPT).derive(password.encode("utf-8"))
        nonce = os.urandom(12)
        self._header.update({"mode": "master", "salt": _b64(salt), "kdf": dict(_SCRYPT), "key_nonce": _b64(nonce),
                             "wrapped_key": _b64(AESGCM(kek).encrypt(nonce, self._key, _AAD_KEY))})

    def set_master_password(self, new_password: str) -> bool:
        """Switch to (or change) master-password protection. Vault must be unlocked."""
        if self._key is None or not new_password:
            return False
        self._wrap_with_password(new_password)
        self._save()
        self._poke()
        return True

    def remove_master_password(self) -> bool:
        """Switch back to transparent DPAPI protection. Vault must be unlocked."""
        if self._key is None or not win.IS_WINDOWS:
            return False
        for k in ("salt", "kdf", "key_nonce"):
            self._header.pop(k, None)
        self._header["mode"] = "dpapi"
        self._header["wrapped_key"] = _b64(win.dpapi_protect(self._key))
        self._idle.stop()
        self._save()
        return True

    # ----------------------------------------------------------- persistence
    def _load_entries(self) -> None:
        assert self._key is not None
        h = self._header
        if "data" not in h:
            self._entries, self._never = [], []
            return
        plain = AESGCM(self._key).decrypt(_unb64(h["nonce"]), _unb64(h["data"]), _AAD_DATA)
        payload = json.loads(plain.decode("utf-8"))
        fields = Credential.__dataclass_fields__
        self._entries = [Credential(**{k: v for k, v in e.items() if k in fields}) for e in payload.get("entries", [])]
        self._never = list(payload.get("never", []))

    def _save(self) -> None:
        if self._key is None:
            raise VaultError("Vault is locked")
        payload = json.dumps({"entries": [asdict(e) for e in self._entries], "never": self._never}).encode("utf-8")
        nonce = os.urandom(12)
        self._header["nonce"] = _b64(nonce)
        self._header["data"] = _b64(AESGCM(self._key).encrypt(nonce, payload, _AAD_DATA))
        atomic_write_bytes(self._path, json.dumps(self._header).encode("utf-8"))

    # --------------------------------------------------------------- queries
    def entries(self) -> list[Credential]:
        if not self.ensure_unlocked():
            return []
        return list(self._entries)

    def get(self, cid: str) -> Credential | None:
        if not self.ensure_unlocked():
            return None
        return next((e for e in self._entries if e.id == cid), None)

    def find_for_url(self, url: QUrl | str, space_id: str = "") -> list[Credential]:
        q = url if isinstance(url, QUrl) else QUrl(url)
        host = strip_www(q.host())
        if not host or not self.ensure_unlocked():
            return []
        scheme = q.scheme()
        out = []
        for e in self._entries:
            eq = QUrl(e.origin)
            if strip_www(eq.host()) != host:
                continue
            if eq.scheme() == "https" and scheme != "https":  # never downgrade to http pages
                continue
            if e.space_id and e.space_id != space_id:
                continue
            out.append(e)
        out.sort(key=lambda e: e.last_used, reverse=True)
        return out

    # --------------------------------------------------------------- writes
    def save_credential(self, url: QUrl | str, username: str, password: str, space_id: str = "") -> Credential:
        if not self.ensure_unlocked():
            raise VaultError("Vault is locked")
        q = url if isinstance(url, QUrl) else QUrl(url)
        origin = origin_of(q)
        for e in self._entries:
            if e.origin == origin and e.username == username and e.space_id == space_id:
                e.password = password
                e.updated = time.time()
                self._save()
                self.changed.emit()
                return e
        cred = Credential(origin=origin, username=username, password=password, space_id=space_id)
        self._entries.append(cred)
        self._save()
        self.changed.emit()
        return cred

    def has_exact(self, url: QUrl | str, username: str, password: str, space_id: str = "") -> bool:
        return any(e.username == username and e.password == password for e in self.find_for_url(url, space_id))

    def update(self, cid: str, **fields) -> None:
        e = self.get(cid)
        if not e:
            return
        for k, v in fields.items():
            if hasattr(e, k):
                setattr(e, k, v)
        e.updated = time.time()
        self._save()
        self.changed.emit()

    def remove(self, cid: str) -> None:
        if not self.ensure_unlocked():
            return
        self._entries = [e for e in self._entries if e.id != cid]
        self._save()
        self.changed.emit()

    def mark_used(self, cid: str) -> None:
        e = self.get(cid)
        if e:
            e.last_used = time.time()
            self._save()

    def never_list(self) -> list[str]:
        return list(self._never) if self.ensure_unlocked() else []

    def is_never(self, host: str) -> bool:
        return strip_www(host) in self._never if self.ensure_unlocked() else False

    def add_never(self, host: str) -> None:
        if self.ensure_unlocked() and strip_www(host) not in self._never:
            self._never.append(strip_www(host))
            self._save()
            self.changed.emit()

    def remove_never(self, host: str) -> None:
        if self.ensure_unlocked():
            self._never = [h for h in self._never if h != host]
            self._save()
            self.changed.emit()

    def import_csv(self, path: str) -> int:
        """Import a Chrome / Edge / Firefox password export (name,url,username,password[,note])."""
        if not self.ensure_unlocked():
            raise VaultError("Vault is locked")
        count = 0
        with open(path, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                row = {(k or "").strip().lower(): (v or "") for k, v in row.items()}
                url = row.get("url") or row.get("origin") or ""
                user = row.get("username") or row.get("login") or ""
                pwd = row.get("password") or ""
                if not url or not pwd:
                    continue
                q = QUrl(url)
                if not q.host():
                    continue
                origin = origin_of(q)
                if any(e.origin == origin and e.username == user for e in self._entries):
                    continue
                self._entries.append(Credential(origin=origin, username=user, password=pwd,
                                                note=row.get("note", "") or row.get("notes", "")))
                count += 1
        if count:
            self._save()
            self.changed.emit()
        return count
