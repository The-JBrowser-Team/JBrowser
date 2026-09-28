# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for JBrowser (one-folder build: fast start-up, recommended for Qt WebEngine).
#   pyinstaller JBrowser.spec --noconfirm --clean
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("jbrowser") + [
    "PyQt6.QtWebChannel",      # qwebchannel.js resource + isolated-world password bridge
    "PyQt6.QtPrintSupport",    # printing
    "PyQt6.QtNetwork",
    "PyQt6.QtMultimedia",      # welcome-screen sound effects (QSoundEffect)
    "pywinstyles",
    "cryptography.hazmat.primitives.ciphers.aead",
    "cryptography.hazmat.primitives.kdf.scrypt",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("assets/jbrowser.ico", "assets"), ("assets/jbrowser.png", "assets"),
           ("assets/sounds/intro.wav", "assets/sounds"), ("assets/sounds/click.wav", "assets/sounds")],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PySide2", "PySide6", "matplotlib", "numpy", "IPython"],
    noarchive=False,
)
# Sound effects use Qt's native Windows audio backend (QT_MEDIA_BACKEND=windows), so the large
# FFmpeg media plugin and its libraries are not needed. (Web video uses Chromium's own codecs.)
_FFMPEG = ("ffmpegmediaplugin", "avcodec-", "avformat-", "avutil-", "swresample-", "swscale-")
a.binaries = [b for b in a.binaries if not any(k in b[0].lower().replace("\\", "/") for k in _FFMPEG)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JBrowser",
    icon="assets/jbrowser.ico",
    version="tools/version_info.txt",
    console=False,
    debug=False,
    strip=False,
    upx=False,                 # UPX corrupts Qt WebEngine binaries — keep disabled
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="JBrowser",
)
