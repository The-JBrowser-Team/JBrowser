"""Password-protected ZIP files with AES-256 encryption (the WinZip AES format, AE-2).

Used to export saved passwords: the CSV never touches the disk unencrypted. Python's zipfile module
only knows the old "ZipCrypto" encryption, which is broken (a known-plaintext attack recovers the
key), so this writes WinZip's AES format itself, on top of the `cryptography` package. 7-Zip, WinRAR,
PeaZip, Keka, The Unarchiver and libarchive (Windows' tar.exe) open these files; Windows Explorer's
built-in "Extract All" does not support AES encryption.

Format (APPNOTE.TXT section 7.2, and WinZip's "AES Encryption Information"):
  * compression method 99, with an extra field 0x9901 holding the vendor version (2 = AE-2), "AE",
    the key strength (3 = 256 bits) and the real compression method (8 = deflate);
  * the key is PBKDF2-HMAC-SHA1(password, 16-byte salt, 1000 iterations), 66 bytes long: the AES key,
    the HMAC key and a 2-byte password check;
  * the data is AES in counter mode with a 128-bit little-endian counter starting at 1, followed by the
    first 10 bytes of HMAC-SHA1 over the encrypted data. AE-2 stores no CRC (it could leak information).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import struct
import time
import zlib
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_SALT_LEN = 16            # AES-256
_KEY_LEN = 32
_ITERATIONS = 1000        # fixed by the format
_AUTH_LEN = 10
_METHOD_AES = 99
_EXTRA_AES = 0x9901
_FLAG_ENCRYPTED = 0x0001
_FLAG_UTF8 = 0x0800


class ZipPasswordError(ValueError):
    """The password is wrong (or the file was changed)."""


def _derive(password: str, salt: bytes) -> tuple[bytes, bytes, bytes]:
    dk = hashlib.pbkdf2_hmac("sha1", password.encode("utf-8"), salt, _ITERATIONS, dklen=2 * _KEY_LEN + 2)
    return dk[:_KEY_LEN], dk[_KEY_LEN:2 * _KEY_LEN], dk[2 * _KEY_LEN:]


def _ctr(key: bytes, data: bytes) -> bytes:
    """AES-CTR as WinZip defines it: a 128-bit little-endian counter starting at 1 (cryptography's CTR
    mode counts big-endian, so the key stream is made with ECB)."""
    if not data:
        return b""
    blocks = (len(data) + 15) // 16
    counters = b"".join(i.to_bytes(16, "little") for i in range(1, blocks + 1))
    # ECB here only encrypts the counter blocks: together with the XOR below this *is* CTR mode.
    enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()  # noqa: S305
    stream = (enc.update(counters) + enc.finalize())[:len(data)]
    return (int.from_bytes(data, "little") ^ int.from_bytes(stream, "little")).to_bytes(len(data), "little")


def _dos_time(ts: float) -> tuple[int, int]:
    t = time.localtime(ts)
    return ((t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2),
            ((max(t.tm_year, 1980) - 1980) << 9) | (t.tm_mon << 5) | t.tm_mday)


def write_encrypted_zip(path: str, files: dict[str, bytes], password: str) -> None:
    """Write ``files`` (name → content) to ``path`` as an AES-256 encrypted, deflated ZIP."""
    if not password:
        raise ValueError("A password is needed")
    local, central = bytearray(), bytearray()
    dos_time, dos_date = _dos_time(time.time())
    extra = struct.pack("<HHH2sBH", _EXTRA_AES, 7, 2, b"AE", 3, 8)   # AE-2, AES-256, deflate
    for name, content in files.items():
        raw_name = name.encode("utf-8")
        flags = _FLAG_ENCRYPTED | (_FLAG_UTF8 if not name.isascii() else 0)
        comp = zlib.compressobj(9, zlib.DEFLATED, -15)
        packed = comp.compress(content) + comp.flush()
        salt = os.urandom(_SALT_LEN)
        key, mac_key, check = _derive(password, salt)
        cipher = _ctr(key, packed)
        auth = hmac.new(mac_key, cipher, hashlib.sha1).digest()[:_AUTH_LEN]
        body = salt + check + cipher + auth
        offset = len(local)
        local += struct.pack("<IHHHHHIIIHH", 0x04034B50, 51, flags, _METHOD_AES, dos_time, dos_date,
                             0, len(body), len(content), len(raw_name), len(extra))
        local += raw_name + extra + body
        central += struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 63, 51, flags, _METHOD_AES, dos_time, dos_date,
                               0, len(body), len(content), len(raw_name), len(extra), 0, 0, 0, 0x20, offset)
        central += raw_name + extra
    end = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(files), len(files), len(central), len(local), 0)
    data = bytes(local + central + end)
    tmp = path + ".part"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


@dataclass
class _Entry:
    name: str
    flags: int
    method: int
    crc: int
    comp_size: int
    size: int
    offset: int
    extra: bytes


def _entries(data: bytes) -> list[_Entry]:
    pos = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
    if pos < 0:
        raise ValueError("This is not a ZIP file")
    _sig, _d, _dc, _n, total, cd_size, cd_offset, _cl = struct.unpack_from("<IHHHHIIH", data, pos)
    out, p = [], cd_offset
    for _ in range(total):
        if data[p:p + 4] != b"PK\x01\x02":
            raise ValueError("The ZIP file is damaged")
        (_s, _vm, _vn, flags, method, _t, _dt, crc, comp_size, size, nlen, xlen, clen, _ds, _ia, _ea,
         offset) = struct.unpack_from("<IHHHHHHIIIHHHHHII", data, p)
        raw = data[p + 46:p + 46 + nlen]
        name = raw.decode("utf-8" if flags & _FLAG_UTF8 else "cp437")
        out.append(_Entry(name, flags, method, crc, comp_size, size, offset, data[p + 46 + nlen:p + 46 + nlen + xlen]))
        p += 46 + nlen + xlen + clen
    return out


def _aes_field(extra: bytes) -> tuple[int, int, int]:
    """(vendor version, key strength, real compression method) from the 0x9901 extra field."""
    p = 0
    while p + 4 <= len(extra):
        hid, size = struct.unpack_from("<HH", extra, p)
        if hid == _EXTRA_AES and size >= 7:
            version, vendor, strength, method = struct.unpack_from("<H2sBH", extra, p + 4)
            if vendor == b"AE":
                return version, strength, method
        p += 4 + size
    raise ValueError("Unsupported ZIP encryption")


def read_zip(path: str, password: str = "") -> dict[str, bytes]:
    """Read every file of a ZIP: plain, or AES encrypted (AE-1/AE-2, any key strength).
    Raises ZipPasswordError for a wrong password and ValueError for anything unsupported."""
    with open(path, "rb") as fh:
        data = fh.read()
    files: dict[str, bytes] = {}
    for e in _entries(data):
        if e.name.endswith("/"):
            continue
        if data[e.offset:e.offset + 4] != b"PK\x03\x04":
            raise ValueError("The ZIP file is damaged")
        nlen, xlen = struct.unpack_from("<HH", data, e.offset + 26)
        start = e.offset + 30 + nlen + xlen
        body = data[start:start + e.comp_size]
        method = e.method
        if e.flags & _FLAG_ENCRYPTED:
            if method != _METHOD_AES:
                raise ValueError("This ZIP uses the old ZipCrypto encryption, which JBrowser doesn't read")
            version, strength, method = _aes_field(e.extra)
            key_len = {1: 16, 2: 24, 3: 32}.get(strength)
            if not key_len:
                raise ValueError("Unsupported AES key strength")
            salt_len = key_len // 2
            salt, check = body[:salt_len], body[salt_len:salt_len + 2]
            cipher, auth = body[salt_len + 2:-_AUTH_LEN], body[-_AUTH_LEN:]
            dk = hashlib.pbkdf2_hmac("sha1", password.encode("utf-8"), salt, _ITERATIONS, dklen=2 * key_len + 2)
            key, mac_key = dk[:key_len], dk[key_len:2 * key_len]
            if not hmac.compare_digest(dk[2 * key_len:], check):
                raise ZipPasswordError("The password is wrong")
            if not hmac.compare_digest(hmac.new(mac_key, cipher, hashlib.sha1).digest()[:_AUTH_LEN], auth):
                raise ZipPasswordError("The password is wrong, or the file was changed")
            body = _ctr(key, cipher)             # AES() takes 128-, 192- and 256-bit keys alike
            check_crc = version == 1
        else:
            check_crc = True
        if method == 8:
            content = zlib.decompress(body, -15)
        elif method == 0:
            content = body
        else:
            raise ValueError(f"Unsupported compression method {method}")
        if check_crc and zlib.crc32(content) & 0xFFFFFFFF != e.crc:
            raise ValueError(f"{e.name} is damaged (CRC mismatch)")
        files[e.name] = content
    return files
