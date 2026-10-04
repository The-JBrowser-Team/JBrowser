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
           ("assets/sounds/intro.wav", "assets/sounds"), ("assets/sounds/click.wav", "assets/sounds"),
           # Reading mode: Mozilla Readability (Apache-2.0), loaded by jbrowser/engine/reader.py
           ("jbrowser/engine/vendor/readability/Readability.js", "jbrowser/engine/vendor/readability"),
           ("jbrowser/engine/vendor/readability/Readability-readerable.js", "jbrowser/engine/vendor/readability"),
           ("jbrowser/engine/vendor/readability/LICENSE.md", "jbrowser/engine/vendor/readability")],
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

# Qt modules JBrowser never loads. The PyQt6 hooks bring them in with the QML plugins of Qt WebEngine
# and Qt Multimedia, but a widgets app needs none of them. (Qt6Quick, Qt6Qml and Qt6QuickWidgets
# stay: Qt6WebEngineCore links against them.) Together with the files below this saves ~170 MB
# on disk and ~45 MB in the installer.
_UNUSED_QT = ("qt6quick3d", "qt6quickcontrols2", "qt6quickdialogs2", "qt6quicktemplates2", "qt6quickparticles",
              "qt6quickeffects", "qt6quickshapes", "qt6quicklayouts", "qt6quicktest", "qt6quicktimeline",
              "qt6quickvectorimage", "qt6pdf", "qt6shadertools", "qt6spatialaudio", "qt6remoteobjects",
              "qt6sensors", "qt6texttospeech", "qt6statemachine", "qt6test.",
              "qt6webenginequick", "qt6webchannelquick", "qt6positioningquick", "qt6multimediaquick",
              "qt6websockets", "qt6serialport")
# Plugins for things JBrowser never does: TIFF / TGA / WBMP / ICNS images, off-screen and minimal platforms,
# network touch input (TUIO) and serial-port GPS receivers (NMEA, the only user of Qt6SerialPort).
_UNUSED_PLUGINS = {"qtiff.dll", "qtga.dll", "qwbmp.dll", "qicns.dll", "qoffscreen.dll", "qminimal.dll",
                   "qtuiotouchplugin.dll", "qtposition_nmea.dll"}


def _needed(dest: str) -> bool:
    d = dest.lower().replace("\\", "/")
    name = d.rsplit("/", 1)[-1]
    if "/qt6/qml/" in d or d.startswith("pyqt6/qt6/qml"):
        return False                                   # QML modules: not used by a widgets app
    if name.startswith(_UNUSED_QT) or name == "qpdf.dll":   # qpdf.dll: the PDF image plugin needs Qt6Pdf
        return False
    if name in _UNUSED_PLUGINS:
        return False
    if name.endswith((".debug.pak", ".debug.bin")):
        return False                                   # debug-build copies; the release engine reads the others
    if "/qt6/translations/" in d:
        # The UI is English: keep only Chromium's English strings (en-GB also covers en-AU etc.).
        return name in ("en-us.pak", "en-gb.pak")
    return True


a.binaries = [b for b in a.binaries if _needed(b[0])]
a.datas = [d for d in a.datas if _needed(d[0])]
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
