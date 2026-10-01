"""Render the JBrowser logo to assets/jbrowser.ico (multi-resolution, PNG-compressed entries), and the
website's icons to site/static/img/icons/ (PNG favicons in multiples of 48 px, as Google Search asks
for, plus the touch and web-app icons).

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


SITE_ICONS = {"favicon-48.png": 48, "favicon-96.png": 96, "favicon-192.png": 192, "icon-512.png": 512,
              "apple-touch-icon.png": 180}


def build_site_icons(folder: Path) -> None:
    from jbrowser.ui.icons import logo_pixmap

    folder.mkdir(parents=True, exist_ok=True)
    for name, size in SITE_ICONS.items():
        logo_pixmap(size).save(str(folder / name), "PNG")
    print(f"Wrote {len(SITE_ICONS)} website icons to {folder}")


LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="JBrowser">
  <!-- The JBrowser mark, as drawn by paint_logo() in jbrowser/ui/icons.py. Written by tools/make_icon.py;
       the "J" is a path, so the logo looks the same wherever it is drawn (no font needed). -->
  <defs>
    <linearGradient id="jb-bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#5b8cff"/>
      <stop offset="0.55" stop-color="#8a5cff"/>
      <stop offset="1" stop-color="#ff5c9d"/>
    </linearGradient>
    <linearGradient id="jb-hi" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#fff" stop-opacity="0.27"/>
      <stop offset="1" stop-color="#fff" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <rect width="100" height="100" rx="26" fill="url(#jb-bg)"/>
  <rect width="100" height="50" rx="26" fill="url(#jb-hi)"/>
  <rect x="14" y="27" width="22" height="46" rx="3.5" fill="#fff" fill-opacity="0.43"/>
  <rect x="40" y="27" width="30" height="46" rx="3.5" fill="#fff"/>
  <rect x="74" y="27" width="14" height="46" rx="3.5" fill="#fff" fill-opacity="0.43"/>
  <path fill="#6a5cff" d="{j}"/>
  <line x1="20" y1="82" x2="80" y2="82" stroke="#fff" stroke-opacity="0.59" stroke-width="2.5" stroke-linecap="round"/>
</svg>
"""


def build_logo_svg(out: Path) -> None:
    """The site's SVG logo, with the "J" placed as paint_logo() places it on the centre card."""
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import QFont, QFontMetricsF, QPainterPath

    font = QFont("Segoe UI Variable Display")
    font.setBold(True)
    font.setPixelSize(33)
    card = QRectF(40, 27, 30, 46)
    fm = QFontMetricsF(font)
    # Where QPainter.drawText(card, AlignCenter, "J") puts the baseline.
    x = card.center().x() - fm.horizontalAdvance("J") / 2
    y = card.center().y() + (fm.ascent() - fm.descent()) / 2
    path = QPainterPath()
    path.addText(QPointF(x, y), font, "J")
    cmds = []
    i = 0
    while i < path.elementCount():
        e = path.elementAt(i)
        if e.type == QPainterPath.ElementType.MoveToElement:
            cmds.append(f"M{e.x:.2f} {e.y:.2f}")
        elif e.type == QPainterPath.ElementType.LineToElement:
            cmds.append(f"L{e.x:.2f} {e.y:.2f}")
        elif e.type == QPainterPath.ElementType.CurveToElement:
            c2, end = path.elementAt(i + 1), path.elementAt(i + 2)
            cmds.append(f"C{e.x:.2f} {e.y:.2f} {c2.x:.2f} {c2.y:.2f} {end.x:.2f} {end.y:.2f}")
            i += 2
        i += 1
    d = " ".join(cmds)          # filled shapes close themselves
    out.write_text(LOGO_SVG.replace("{j}", d), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    build_ico(ROOT / "assets" / "jbrowser.ico")
    build_site_icons(ROOT / "site" / "static" / "img" / "icons")
    build_logo_svg(ROOT / "site" / "static" / "img" / "logo.svg")
