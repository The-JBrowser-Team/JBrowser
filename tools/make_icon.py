"""Render the JBrowser logo to assets/jbrowser.ico (multi-resolution, PNG-compressed entries).

Usage:  python tools/make_icon.py
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PyQt6.QtGui import QGuiApplication  # noqa: E402

SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


def build_ico(out: Path) -> None:
    from jbrowser.ui.icons import logo_pixmap

    blobs = []
    for size in SIZES:
        pm = logo_pixmap(size)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pm.save(buf, "PNG")
        buf.close()
        blobs.append((size, bytes(ba)))
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries = b""
    data = b""
    for size, png in blobs:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(header + entries + data)
    (out.parent / "jbrowser.png").write_bytes(blobs[-1][1])
    print(f"Wrote {out} ({len(blobs)} sizes)")


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    build_ico(ROOT / "assets" / "jbrowser.ico")
