"""Photograph the real app for the website, then convert the pictures for the site.

Runs JBrowser from source with a throw-away profile, puts a full-screen gradient behind a
1600 x 1000 window and captures it from the screen, so Acrylic shows the gradient through the
glass, at the display's full resolution. It shoots the canvas, the Gallery, the Lazy Toolbar, a
split view, the site information panel, stacked cards and the stack picker, reading mode, the ten
colour tints (over a neutral backdrop, where the light wash shows honestly), light mode, an
incognito space and the welcome. The pictures go to
``site/static/img/shots/`` as WebP (1280 px, 1920 px and full size) plus ``og-image.jpg`` for link
previews.

    .\\.venv\\Scripts\\python.exe tools\\site_screenshots.py

It takes about two and a half minutes and loads real web pages. Leave the mouse and keyboard
alone meanwhile: the window is kept in front of everything while it is photographed.
Windows only. The PNG originals are kept in ``%TEMP%\\jbrowser-shots``.
"""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOTS = Path(tempfile.gettempdir()) / "jbrowser-shots"
DEST = ROOT / "site" / "static" / "img" / "shots"
W, H, MARGIN = 1600, 1000, 72          # window size and the gradient around it (logical pixels)

HOME = ["https://www.openstreetmap.org/#map=13/-33.8600/151.2100", "https://en.wikipedia.org/wiki/Aurora",
        "https://github.com/The-JBrowser-Team/JBrowser", "https://developer.mozilla.org/en-US/"]
WORK = ["https://docs.python.org/3/", "https://www.python.org/"]
OTHER = ["https://en.wikipedia.org/wiki/Great_Barrier_Reef"]
READING = "https://en.wikipedia.org/wiki/Coral_reef"       # an article that opens with text (reading mode)
INCOGNITO = ["https://en.wikipedia.org/wiki/Milky_Way", "https://www.openstreetmap.org/#map=5/64.5/17.0"]
FAVOURITES = [("https://github.com/", "GitHub"), ("https://en.wikipedia.org/", "Wikipedia"),
              ("https://developer.mozilla.org/", "MDN"), ("https://www.openstreetmap.org/", "OpenStreetMap")]
TINTS = ("none", "rose", "coral", "amber", "lime", "mint", "teal", "sky", "indigo", "violet", "slate")

# (top-left colour, bottom-right colour, [((x, y), colour, alpha, radius)]) of the backdrop.
BACKDROPS = {
    "dark": ("#1c2a6b", "#5a2466", [((0.18, 0.22), "#4f7dff", 0.95, 0.55), ((0.78, 0.18), "#8a5cff", 0.85, 0.5),
                                    ((0.86, 0.86), "#ff4f93", 0.8, 0.55), ((0.12, 0.9), "#18b7a0", 0.55, 0.45)]),
    "light": ("#dfe8ff", "#fbe3f1", [((0.2, 0.2), "#9cbcff", 0.9, 0.6), ((0.8, 0.2), "#cdb0ff", 0.85, 0.5),
                                     ((0.85, 0.85), "#ffb0cf", 0.85, 0.55), ((0.12, 0.88), "#a6ecd9", 0.8, 0.45)]),
    "neutral": ("#2a2b31", "#3a3b43", [((0.25, 0.2), "#4a4b55", 0.8, 0.55), ((0.8, 0.85), "#1d1e22", 0.9, 0.5)]),
}


# ------------------------------------------------------------------------------ Win32 helpers
def _user32():
    u = ctypes.windll.user32
    u.GetForegroundWindow.restype = ctypes.c_void_p
    return u


def _hwnd(w) -> ctypes.c_void_p:
    return ctypes.c_void_p(int(w.winId()))


def topmost(w, on: bool = True) -> None:
    """Keep ``w`` above other applications' windows (HWND_TOPMOST), without activating it."""
    _user32().SetWindowPos(_hwnd(w), ctypes.c_void_p(-1 if on else -2), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)


def to_front(w) -> None:
    """Make ``w`` the active window: system backdrops only show on active windows."""
    u = _user32()
    fg = u.GetForegroundWindow()
    fg_thread = u.GetWindowThreadProcessId(ctypes.c_void_p(fg), None) if fg else 0
    me = ctypes.windll.kernel32.GetCurrentThreadId()
    attached = bool(fg_thread and fg_thread != me and u.AttachThreadInput(me, fg_thread, True))
    u.SetForegroundWindow(_hwnd(w))
    u.BringWindowToTop(_hwnd(w))
    if attached:
        u.AttachThreadInput(me, fg_thread, False)
    w.activateWindow()


def is_front(w) -> bool:
    return int(_user32().GetForegroundWindow() or 0) == int(w.winId())


# ------------------------------------------------------------------------------ the capture run
def capture() -> None:
    """Runs inside JBrowser's process: schedules the steps once the window is up."""
    from PyQt6.QtCore import QEventLoop, QPointF, QRect, Qt, QTimer, QUrl
    from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QRadialGradient
    from PyQt6.QtWidgets import QApplication, QWidget

    class Stage(QWidget):
        """A full-screen gradient behind the window being photographed."""

        def __init__(self):
            super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                             | Qt.WindowType.WindowDoesNotAcceptFocus)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.key = "dark"

        def set_backdrop(self, key: str) -> None:
            self.key = key
            self.update()

        def paintEvent(self, _e) -> None:
            a, b, blobs = BACKDROPS[self.key]
            p = QPainter(self)
            w, h = self.width(), self.height()
            lg = QLinearGradient(0, 0, w, h)
            lg.setColorAt(0, QColor(a))
            lg.setColorAt(1, QColor(b))
            p.fillRect(self.rect(), lg)
            for (fx, fy), col, alpha, radius in blobs:
                rg = QRadialGradient(QPointF(w * fx, h * fy), max(w, h) * radius)
                c0, c1 = QColor(col), QColor(col)
                c0.setAlphaF(alpha)
                c1.setAlphaF(0)
                rg.setColorAt(0, c0)
                rg.setColorAt(1, c1)
                p.fillRect(self.rect(), rg)
            p.end()

    app = QApplication.instance()
    win = next(w for w in app.topLevelWidgets() if type(w).__name__ == "MainWindow")
    ctx, ui, st = win.ctx, win.ui, win.ctx.state
    s = ctx.settings
    screen = app.primaryScreen().geometry()
    stage = Stage()
    home, work, other = st.spaces[0], st.spaces[1], st.spaces[2]
    x0, y0 = screen.x() + (screen.width() - W) // 2, screen.y() + (screen.height() - H) // 2

    def wait(ms: int) -> None:
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def cap(name: str, keep_focus: bool = False) -> None:
        from jbrowser.ui.card import StatusBubble
        for b in win.findChildren(StatusBubble):            # the pointer may rest on a link
            b.hide()
        if not keep_focus and win._onboarding is None and win.stack.current() is not None:
            win.stack.current().setFocus()                  # no focus rings inside pages
        wait(350)
        for b in win.findChildren(StatusBubble):
            b.hide()
        g = win.frameGeometry()
        pm = app.primaryScreen().grabWindow(0, g.x() - MARGIN, g.y() - MARGIN, g.width() + 2 * MARGIN,
                                            g.height() + 2 * MARGIN)
        pm.save(str(SHOTS / f"{name}.png"))
        print(f"  {name}: {pm.width()} x {pm.height()}{'' if is_front(win) else '  (window was not in front!)'}",
              flush=True)

    def canvas(space):
        return win.stack.canvas(space.id)

    def halves(space, first: int = 0) -> None:
        for t in space.tabs:
            t.update(width=0.5)
        st.set_active_tab(space.tabs[first].id)
        canvas(space).scroll_to(0, animated=False)

    def front() -> None:
        topmost(win)
        to_front(win)

    def ensure_lists() -> None:
        """The privacy shot needs the real filter lists: download them first if the profile has none."""
        if ctx.privacy.filters is None:
            print("  downloading the filter lists...", flush=True)
            ctx.privacy.update_blocklist(manual=False)
            for _ in range(120):                              # up to a minute
                wait(500)
                if ctx.privacy.filters is not None:
                    break
        print(f"  filter engine: {ctx.privacy.filters.network_count if ctx.privacy.filters else 0} rules", flush=True)

    def setup() -> None:
        ensure_lists()
        win.lazy.close_overlay()
        for key, value in (("appearance.theme", "dark"), ("appearance.material", "acrylic"),
                           ("appearance.tint", "none"), ("appearance.favorites_bar", False)):
            s.set(key, value)
        win.showNormal()
        win.setGeometry(QRect(x0, y0, W, H))
        for space, urls in ((home, HOME), (work, WORK), (other, OTHER)):
            for u in urls:
                ui.open_url(QUrl(u), "new", space_id=space.id)

    def snapshots() -> None:
        c = canvas(home)
        for tid in c.visible_tab_ids():
            if tid in c.cards:
                c.cards[tid].take_snapshot()                 # thumbnails for the Gallery

    def scroll_home_to(index: int) -> None:
        g = canvas(home).geo(home.tabs[index].id)
        canvas(home).scroll_to(max(0.0, g[0] - 12) if g else 0.0, animated=False)

    def stage_on() -> None:
        stage.set_backdrop("dark")
        stage.setGeometry(screen)
        stage.show()
        topmost(stage)
        front()

    def site_info() -> None:
        ui.show_site_info_anchored()
        for w in app.topLevelWidgets():
            if w.isVisible() and w.isWindow() and w not in (win, stage):
                topmost(w)                                   # popups must sit above the topmost window

    def close_popups() -> None:
        for w in app.topLevelWidgets():
            if w.isVisible() and type(w).__name__ == "SiteInfoPopup":
                w.close()

    def split() -> None:
        st.set_active_tab(home.tabs[1].id)
        ui.split(3)
        canvas(home).scroll_to(0, animated=False)

    def lazy() -> None:
        ui.open_lazy_toolbar("new", "py")
        win.lazy.edit.deselect()
        win.lazy.edit.end(False)

    def stacked() -> None:
        """2.0: two cards stacked in a column next to a half-width card."""
        halves(home)
        st.stack_tab(home.tabs[1].id, home.tabs[0].id)
        st.set_active_tab(home.tabs[0].id)
        canvas(home).scroll_to(0, animated=False)

    def picker() -> None:
        st.set_active_tab(home.tabs[2].id)
        canvas(home).open_stack_picker(home.tabs[2].id)
        if canvas(home).picker is not None:
            canvas(home).picker.input.setText("wiki")

    def unstacked() -> None:
        canvas(home).close_stack_picker(animated=False)
        for t in list(home.tabs):
            if t.stack:
                st.unstack(t.id)
        halves(home)

    def open_article() -> None:
        st.set_active_tab(home.tabs[0].id)
        ui.open_url(QUrl(READING), "new", space_id=home.id)

    def reading() -> None:
        article = next(t for t in home.tabs if t.url.startswith(READING))
        for t in home.tabs:
            t.update(width=0.62 if t is article else 0.38)
        st.set_active_tab(article.id)
        canvas(home).ensure_visible(article.id, align="left", animated=False)
        ui.set_reading(article.id, True)

    def end_reading() -> None:
        for t in list(home.tabs):
            if t.url.startswith(READING):
                ui.close_tab(t.id, remember=False)
        halves(home)

    def incognito_cards() -> None:
        win.lazy.close_overlay()
        for u in INCOGNITO:
            ui.open_url(QUrl(u), "new")

    def welcome(step: str):
        def go() -> None:
            from jbrowser.ui.onboarding import STEPS
            ob = win._onboarding
            if ob is not None:
                if ob.phase == "intro":
                    ob.end_intro()
                ob.go_to(STEPS.index(step))
        return go

    def finish_welcome() -> None:
        if win._onboarding is not None:
            win._onboarding.finish()

    def cleanup() -> None:
        topmost(win, False)
        stage.hide()
        win.close()

    steps = [
        (400, setup),
        (14000, lambda: ui.select_space(work.id)), (4500, lambda: ui.select_space(other.id)),
        (4000, lambda: ui.select_space(home.id)),
        (2500, lambda: [ctx.favourites.add(u, t) for u, t in FAVOURITES]),
        (500, lambda: scroll_home_to(2)), (3000, snapshots), (300, lambda: halves(home)), (2500, snapshots),
        (300, stage_on), (2500, front),
        (1200, lambda: cap("hero_dark")),
        (300, lambda: ui.toggle_gallery(True)), (2600, lambda: cap("gallery_all_dark")),
        (200, lambda: win.gallery.close_gallery()),
        (900, lazy), (2500, lambda: cap("lazy_toolbar_dark", keep_focus=True)), (200, win.lazy.close_overlay),
        (700, split), (3400, lambda: cap("split_dark")), (200, lambda: halves(home)),
        (600, lambda: (st.set_active_tab(home.tabs[2].id), canvas(home).ensure_visible(home.tabs[2].id, animated=False))),
        (1500, site_info), (1200, lambda: cap("site_info_dark")), (200, close_popups),
        (600, stacked), (2600, lambda: cap("stack_dark")), (300, picker),
        (1400, lambda: cap("stack_picker_dark", keep_focus=True)), (300, unstacked),
        (300, open_article), (6000, reading), (2600, lambda: cap("reading_dark")), (300, end_reading),
        (600, lambda: halves(home)), (200, lambda: stage.set_backdrop("neutral")),
        *[step for key in TINTS for step in ((250, lambda k=key: s.set("appearance.tint", k)),
                                             (1100, lambda k=key: cap(f"tint_{k}")))],
        (250, lambda: s.set("appearance.tint", "none")), (200, lambda: stage.set_backdrop("dark")),
        (400, lambda: (ui.select_space(work.id), halves(work))), (2500, lambda: cap("work_dark")),
        (300, lambda: halves(home)),
        (300, lambda: (s.set("appearance.theme", "light"), stage.set_backdrop("light"))), (2200, front),
        (1200, lambda: cap("hero_light")),
        (300, lambda: ui.toggle_gallery(True)), (2600, lambda: cap("gallery_all_light")),
        (200, lambda: win.gallery.close_gallery()),
        (600, lambda: (s.set("appearance.theme", "dark"), stage.set_backdrop("dark"))),
        (1500, lambda: ui.new_space(True)), (1200, incognito_cards),
        (7000, lambda: halves(st.active_space)), (600, front), (1500, lambda: cap("incognito")),
        (300, lambda: ui.select_space(home.id)), (500, front),
        (400, lambda: win.start_onboarding(replay=True)), (1200, welcome("story3")),
        (3200, lambda: cap("welcome_gallery")), (300, welcome("look")), (2800, lambda: cap("welcome_look")),
        (300, finish_welcome), (1800, cleanup),
    ]

    def run(i: int = 0) -> None:
        if i >= len(steps):
            return
        delay, fn = steps[i]

        def go() -> None:
            try:
                fn()
            except Exception:
                traceback.print_exc()
            run(i + 1)
        QTimer.singleShot(delay, go)

    print("Capturing (about two and a half minutes; please don't touch the mouse or keyboard)...", flush=True)
    run()


def run_capture(profile: Path) -> int:
    """Start JBrowser from source in this process with ``capture()`` scheduled after start-up."""
    sys.path.insert(0, str(ROOT))
    os.environ["JBROWSER_SKIP_WELCOME"] = "1"
    os.environ["JBROWSER_SKIP_UPDATES"] = "1"
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    import jbrowser.app as app_module

    original_exec = QApplication.exec

    def exec_with_capture(*_a, **_k):
        QTimer.singleShot(1500, capture)
        return original_exec()

    QApplication.exec = exec_with_capture
    watchdog = threading.Timer(420, lambda: os._exit(3))      # never hang forever
    watchdog.daemon = True
    watchdog.start()
    return app_module.run(["jbrowser", "--profile-dir", str(profile)])


# ------------------------------------------------------------------------------ conversion
def convert() -> None:
    """PNG originals in SHOTS â†’ WebP files for the site (run in its own process)."""
    from PyQt6.QtCore import QRect, Qt
    from PyQt6.QtGui import QGuiApplication, QImage

    global _qt_app
    _qt_app = QGuiApplication(sys.argv[:1])     # image plug-ins (WebP) need an application object
    DEST.mkdir(parents=True, exist_ok=True)
    total = 0

    def save(img: QImage, name: str, width: int | None, quality: int) -> None:
        nonlocal total
        out = img if width is None or width >= img.width() else \
            img.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
        path = DEST / f"{name.replace('_', '-')}-{'full' if width is None else width}.webp"
        if not out.save(str(path), "WEBP", quality):
            raise SystemExit(f"Could not write {path}")
        total += path.stat().st_size

    showcase = ["hero_dark", "hero_light", "gallery_all_dark", "gallery_all_light", "lazy_toolbar_dark", "split_dark",
                "site_info_dark", "work_dark", "incognito", "welcome_look", "welcome_gallery", "stack_dark",
                "stack_picker_dark", "reading_dark"]
    for name in showcase:
        img = QImage(str(SHOTS / f"{name}.png"))
        if img.isNull():
            raise SystemExit(f"Missing screenshot: {name}.png")
        for width, quality in ((1280, 82), (1920, 82), (None, 86)):
            save(img, name, width, quality)
    for key in TINTS:
        # The tint shows most in the sidebar and the title bar: the window's top-left corner, larger.
        img = QImage(str(SHOTS / f"tint_{key}.png")).copy(QRect(0, 0, 1640, 1120))
        save(img, f"tint_{key}", 1280, 84)
        save(img, f"tint_{key}", None, 86)
    hero = QImage(str(SHOTS / "hero_dark.png"))
    h = int(hero.width() / (1200 / 630))
    og = hero.copy(QRect(0, max(0, (hero.height() - h) // 2), hero.width(), h)).scaled(
        1200, 630, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    og.save(str(DEST / "og-image.jpg"), "JPEG", 88)
    print(f"Wrote {len(showcase) * 3 + len(TINTS) * 2 + 1} files to {DEST} ({total / 1048576:.1f} MB)")


def main() -> int:
    if sys.platform != "win32":
        sys.exit("Screenshots are taken on Windows (the app uses Windows backdrops).")
    if "--convert" in sys.argv:
        convert()
        return 0
    if "--capture" in sys.argv:
        code = run_capture(Path(sys.argv[sys.argv.index("--capture") + 1]))
        sys.stdout.flush()
        os._exit(code)                  # skip interpreter teardown: Qt WebEngine is already shut down
    SHOTS.mkdir(parents=True, exist_ok=True)
    profile = Path(tempfile.mkdtemp(prefix="jbrowser-shots-profile-"))
    (profile / "settings.json").write_text(json.dumps({"appearance.sounds": False, "appearance.favorites_bar": False,
                                                       "onboarding.version": 99}), encoding="utf-8")
    appdata = Path(os.environ.get("APPDATA", "")) / "JBrowser"
    for name in ("blocklist.txt", "filters.txt", "threats.txt"):     # the downloaded lists, so blocking counts
        if (appdata / name).exists():
            shutil.copy2(appdata / name, profile / name)
    code = subprocess.call([sys.executable, __file__, "--capture", str(profile)])
    shutil.rmtree(profile, ignore_errors=True)
    missing = [n for n in ("hero_dark", "welcome_look") if not (SHOTS / f"{n}.png").exists()]
    if code != 0 or missing:
        print(f"The capture did not finish (exit code {code}).")
        return 1
    return subprocess.call([sys.executable, __file__, "--convert"])


if __name__ == "__main__":
    sys.exit(main())
