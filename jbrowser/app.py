"""Application bootstrap: environment, single instance, services, window, orderly shutdown."""
from __future__ import annotations

import argparse
import getpass
import gc
import hashlib
import json
import logging
import logging.handlers
import os
import sys
import traceback

from jbrowser import APP_ID, APP_MUTEX, APP_NAME, ORG_NAME, __version__
from jbrowser.core.jsonstore import read_json
from jbrowser.paths import AppPaths

log = logging.getLogger("jbrowser")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog=APP_NAME, add_help=True)
    p.add_argument("urls", nargs="*", help="URLs or search terms to open")
    p.add_argument("--profile-dir", help="Keep all data in this folder (portable mode)")
    p.add_argument("--incognito", action="store_true", help="Start in a new incognito space")
    p.add_argument("--no-restore", action="store_true", help="Do not restore the previous session's cards")
    p.add_argument("--debug", action="store_true", help="Verbose logging to the console")
    p.add_argument("--wait-pid", type=int, default=0, help=argparse.SUPPRESS)  # restart hand-over
    args, _unknown = p.parse_known_args(argv[1:])  # Qt / Chromium switches pass through
    return args


def _setup_logging(paths: AppPaths, debug: bool) -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    fh = logging.handlers.RotatingFileHandler(paths.logs / "jbrowser.log", maxBytes=2_000_000, backupCount=3,
                                              encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root.addHandler(fh)
    if debug or sys.stderr is not None and os.environ.get("JBROWSER_CONSOLE_LOG"):
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(levelname)-7s %(name)s: %(message)s"))
        root.addHandler(sh)


def _chromium_flags(paths: AppPaths) -> None:
    from jbrowser.services.network import normalize_proxy

    stored = read_json(paths.settings_file, {}) or {}
    flags = ["--log-level=3"]
    cfg = normalize_proxy(stored.get("network.proxy") if isinstance(stored, dict) else None)
    if cfg["mode"] == "manual" and cfg["type"] == "https" and cfg["host"]:
        flags.append(f"--proxy-server=https://{cfg['host']}:{cfg['port']}")
    existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    # A restarted or updated copy inherits this variable from the previous one: drop the flags that
    # copy added itself (e.g. a proxy that has since been removed) and keep only the user's own.
    inherited = os.environ.get("JBROWSER_ADDED_CHROMIUM_FLAGS", "")
    if inherited and existing.endswith(inherited):
        existing = existing[: -len(inherited)].strip()
    added = " ".join(flags)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (existing + " " + added).strip()
    os.environ["JBROWSER_ADDED_CHROMIUM_FLAGS"] = added
    # Composite widget windows through Direct3D 11 from the start. Otherwise the first web
    # card converts the raster window to an RHI window, which recreates the HWND (flicker)
    # and drops the Mica backdrop.
    os.environ.setdefault("QT_WIDGETS_RHI", "1")
    os.environ.setdefault("QT_WIDGETS_RHI_BACKEND", "d3d11")
    # UI sound effects only need the native Windows audio backend (not FFmpeg).
    os.environ.setdefault("QT_MEDIA_BACKEND", "windows")


def _wait_for_process(pid: int, timeout_ms: int = 20000) -> None:
    """Block until the previous instance (restart / factory reset) has fully exited."""
    if not pid or sys.platform != "win32":
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if handle:
        kernel32.WaitForSingleObject(ctypes.c_void_p(handle), timeout_ms)
        kernel32.CloseHandle(ctypes.c_void_p(handle))


_mutex_handle = None


def _hold_app_mutex() -> None:
    """Hold a named mutex for the life of the process so the installer can tell JBrowser is running."""
    global _mutex_handle
    if sys.platform != "win32" or _mutex_handle:
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _mutex_handle = kernel32.CreateMutexW(None, False, APP_MUTEX)


def _relaunch_command(argv: list[str], args: argparse.Namespace) -> tuple[str, list[str]]:
    """Command line that starts a fresh copy of this JBrowser (frozen exe or source checkout)."""
    extra = ["--wait-pid", str(os.getpid())]
    if args.profile_dir:
        extra += ["--profile-dir", os.path.abspath(args.profile_dir)]
    if args.debug:
        extra.append("--debug")
    if getattr(sys, "frozen", False):
        return sys.executable, extra
    main = os.path.abspath(argv[0]) if argv and argv[0].endswith(".py") else ""
    if main:
        return sys.executable, [main] + extra
    return sys.executable, ["-m", "jbrowser"] + extra


def run(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    args = _parse_args(argv)
    _wait_for_process(args.wait_pid)
    paths = AppPaths(args.profile_dir)
    reset_done = False
    if paths.reset_marker.exists():
        paths.factory_reset()
        reset_done = True
    paths.ensure()
    _setup_logging(paths, args.debug)
    log.info("%s %s starting (Python %s)", APP_NAME, __version__, sys.version.split()[0])
    if reset_done:
        log.info("Factory reset completed: all JBrowser data was erased")
    _chromium_flags(paths)
    first_run = not paths.settings_file.exists()

    import PyQt6.QtWebEngineWidgets as _web  # must be imported before QApplication exists
    assert _web
    from PyQt6.QtCore import QCoreApplication, QEvent, Qt, QTimer
    from PyQt6.QtWidgets import QApplication

    from jbrowser.platform import win

    win.set_app_user_model_id(APP_ID)
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")

    from jbrowser.single_instance import SingleInstance

    key = f"{APP_NAME}-{getpass.getuser()}-{hashlib.sha1(str(paths.data).encode()).hexdigest()[:10]}"
    instance = SingleInstance(key)
    payload = {"urls": args.urls, "incognito": args.incognito}
    if instance.notify_existing(json.dumps(payload)):
        log.info("Forwarded launch request to the running instance")
        return 0
    instance.listen()
    _hold_app_mutex()

    from jbrowser.context import AppContext
    from jbrowser.core.settings import Settings
    from jbrowser.ui.icons import app_icon
    from jbrowser.ui.theme import Theme

    app.setWindowIcon(app_icon())
    settings = Settings(paths.settings_file)
    if first_run:
        settings.set("appearance.animations", win.system_animations_enabled())
    theme = Theme(settings)
    ctx = AppContext(paths, settings)
    ctx.theme = theme
    ctx.dns.apply()                                   # before the first profile touches the network
    ctx.proxy.flag_mode = bool(ctx.proxy.startup_flags(settings))
    if not ctx.proxy.flag_mode:
        ctx.proxy.apply(None, force=True)
    restored = ctx.session.restore(False if args.no_restore else None, migrate_from=settings.migrated_from)
    for sid in ctx.session.dropped_spaces:        # retired default spaces from older versions
        paths.wipe_profile(sid)
    if settings.migrated_from < 2:
        ctx.session.save_now()

    from jbrowser.ui.window import MainWindow

    window = MainWindow(ctx)

    def excepthook(etype, value, tb):
        log.error("Unhandled exception:\n%s", "".join(traceback.format_exception(etype, value, tb)))
        try:
            window.toasts.show(f"Something went wrong: {value}"[:120], "error", 4000)
        except Exception:
            pass

    sys.excepthook = excepthook

    def open_request(urls: list[str], incognito: bool) -> None:
        if incognito:
            window.ui.new_space(True)
        for u in urls:
            window.ui.open_url(u, "new")
        if window.isMinimized():
            window.showNormal()
        window.raise_()
        window.activateWindow()

    def on_message(raw: str) -> None:
        try:
            data = json.loads(raw)
        except ValueError:
            return
        open_request(list(data.get("urls") or []), bool(data.get("incognito")))

    instance.received.connect(on_message)
    window.show_restored()
    ctx.session.start()
    from jbrowser.ui.onboarding import ONBOARDING_VERSION

    welcome = (int(settings.get("onboarding.version") or 0) < ONBOARDING_VERSION and not args.urls
               and not args.incognito and not os.environ.get("JBROWSER_SKIP_WELCOME"))
    if welcome:
        QTimer.singleShot(200, window.start_onboarding)
    elif args.incognito or args.urls:
        QTimer.singleShot(0, lambda: open_request(args.urls, args.incognito))
    elif not ctx.state.all_tabs():
        QTimer.singleShot(450, lambda: window.ui.open_lazy_toolbar("new"))
    if reset_done and not welcome:
        QTimer.singleShot(900, lambda: window.toasts.show(
            "JBrowser was reset. Everything is back to how it was on day one.", "sync", 6000))
    elif not restored and not welcome:
        QTimer.singleShot(900, lambda: window.toasts.show(
            "Welcome to JBrowser. Ctrl+T opens a new card, Ctrl+/ shows every shortcut.", "lightbulb", 6000))
    QTimer.singleShot(8000, ctx.threats.maybe_refresh)             # weekly dangerous-site list refresh
    if not os.environ.get("JBROWSER_SKIP_UPDATES"):
        ctx.updater.start()                                        # daily GitHub Releases check
    QTimer.singleShot(12000, ctx.privacy.maybe_update_blocklist)   # weekly tracker list refresh

    code = app.exec()

    # Orderly teardown: views and pages were scheduled for deletion in closeEvent; flush them,
    # then release the profiles (Qt WebEngine requires pages to die before their profile).
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    ctx.profiles.dispose_all()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()
    log.info("%s exited with code %s", APP_NAME, code)
    if ctx.restart_requested:
        from PyQt6.QtCore import QProcess

        instance.close()
        program, arguments = _relaunch_command(argv, args)
        started = QProcess.startDetached(program, arguments, os.getcwd())
        ok = started[0] if isinstance(started, tuple) else bool(started)
        log.info("Restarting: %s %s (%s)", program, " ".join(arguments), "ok" if ok else "failed")
    return code
