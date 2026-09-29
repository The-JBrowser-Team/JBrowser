"""BrowserController: executes user intents against the state store, engine and UI surfaces.

Widgets never mutate state directly; they call into this controller (or run a registered
command), which keeps behaviour consistent between clicks, shortcuts and the Lazy Toolbar.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QPoint, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication
from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest
from PyQt6.QtWidgets import QFileDialog, QInputDialog, QLineEdit, QMenu, QMessageBox

from jbrowser.core.settings import SLEEP_PRESETS
from jbrowser.core.urls import pretty_url, strip_www  # noqa: F401  (strip_www used by site actions)
from jbrowser.models.tab import Tab
from jbrowser.services.network import DEV_PORTS, DNS_MODES, describe_proxy
from jbrowser.ui.widgets import menu_action, submenu

if TYPE_CHECKING:
    from jbrowser.context import AppContext
    from jbrowser.engine.tab_controller import TabController
    from jbrowser.ui.canvas import Canvas
    from jbrowser.ui.card import WebCard
    from jbrowser.ui.window import MainWindow

log = logging.getLogger(__name__)

WIDTH_PRESETS = [(0.25, "25%"), (1 / 3, "33%"), (0.5, "50%"), (2 / 3, "66%"), (0.75, "75%"), (0.8, "80%"), (1.0, "100%")]


class BrowserController(QObject):
    def __init__(self, ctx: "AppContext", window: "MainWindow"):
        super().__init__(window)
        self.ctx = ctx
        self.window = window
        self._fs_card: "WebCard | None" = None
        self._prev_width: dict[str, float] = {}
        self._printers: list = []
        self._dialogs: dict[str, object] = {}

    # ------------------------------------------------------------- lookups
    def canvas(self, space_id: str | None = None) -> "Canvas | None":
        stack = getattr(self.window, "stack", None)
        return stack.canvas(space_id or self.ctx.state.active_space_id) if stack else None

    def card(self, tab_id: str | None) -> "WebCard | None":
        if not tab_id:
            return None
        tab = self.ctx.state.tab(tab_id)
        c = self.canvas(tab.space_id) if tab else None
        return c.cards.get(tab_id) if c else None

    def active_card(self) -> "WebCard | None":
        tab = self.ctx.state.active_tab
        return self.card(tab.id) if tab else None

    def ctrl(self, tab_id: str | None = None) -> "TabController | None":
        tid = tab_id or (self.ctx.state.active_tab.id if self.ctx.state.active_tab else None)
        return self.ctx.engine.controller(tid) if tid else None

    def toast(self, text: str, glyph: str = "info") -> None:
        self.window.toasts.show(text, glyph)

    # --------------------------------------------------------------- cards
    def open_url(self, url: QUrl | str, target: str = "new", space_id: str | None = None,
                 after_tab: str | None = None, index: int | None = None) -> Tab | None:
        st = self.ctx.state
        q = url if isinstance(url, QUrl) else self.ctx.resolve_input(url)
        space = st.space(space_id) if space_id else st.active_space
        if space is None:
            return None
        if target == "current":
            tab = space.active_tab()
            if tab is not None:
                ctrl = self.ctx.engine.controller(tab.id)
                if ctrl is not None:
                    ctrl.load(q)
                    self.activate_card(tab.id, focus=True)
                    return tab
            target = "new"
        if index is not None:
            index = max(0, min(index, len(space.tabs)))
        elif after_tab:
            idx = space.index_of(after_tab)
            if idx >= 0:
                index = idx + 1
        background = target == "background"
        tab = st.add_tab(space.id, q.toString(), index=index, activate=not background,
                         width=self.ctx.settings.get("canvas.default_width"))
        if tab is None:
            return None
        if space.id != st.active_space_id and not background:
            st.set_active_space(space.id)
        if not background:
            QTimer.singleShot(0, lambda tid=tab.id: self.activate_card(tid, focus=True))
        else:
            self.toast(f"Opened in background: {pretty_url(q, keep_path=False)}", "taskview")
        return tab

    def new_blank_card(self) -> None:
        self.open_lazy_toolbar("new")

    def close_tab(self, tab_id: str, remember: bool = True) -> None:
        tab = self.ctx.state.tab(tab_id)
        if tab is None:
            return
        if self._fs_card is not None and self._fs_card.tab.id == tab_id:
            self.window.exit_immersive()
            self._fs_card = None
        ctrl = self.ctx.engine.controller(tab_id)
        history = ctrl.history_bytes() if ctrl and remember else None
        self.ctx.state.remove_tab(tab_id, remember=remember, history=history)
        QTimer.singleShot(0, self.focus_active_card)

    def close_selected(self) -> None:
        tabs = self.ctx.state.selected_tabs()
        for t in tabs:
            self.close_tab(t.id)

    def close_others(self, tab_id: str) -> None:
        space = self.ctx.state.space_of(tab_id)
        if space:
            for t in [t for t in space.tabs if t.id != tab_id and not t.pinned]:
                self.close_tab(t.id)

    def reopen_closed(self) -> None:
        live = {s.id for s in self.ctx.state.spaces if not s.incognito}
        entry = self.ctx.archive.take_latest(live) or self.ctx.archive.take_latest()
        if entry is None:
            self.toast("No recently closed cards", "archive")
            return
        self._reopen(entry)

    def reopen_archive_entry(self, entry_id: str, background: bool = False) -> None:
        entry = self.ctx.archive.take(entry_id)
        if entry is not None:
            self._reopen(entry, background)

    def _reopen(self, entry, background: bool = False) -> None:
        st = self.ctx.state
        space = st.space(entry.space_id)
        if space is None or space.incognito:
            space = st.active_space
        if space is None:
            return
        tab = st.add_tab(space.id, entry.url, width=entry.width or 0.5, title=entry.title,
                         history=entry.history_bytes(), pinned=entry.pinned, activate=not background)
        if tab is None:
            return
        if background:
            self.toast(f"Reopened in the background: {entry.title or pretty_url(entry.url)}"[:90], "archive")
            return
        if tab.space_id != st.active_space_id:
            st.set_active_space(tab.space_id)
        QTimer.singleShot(0, lambda: self.activate_card(tab.id, center=True))

    def show_archive(self, anchor=None) -> None:
        from jbrowser.ui.archive import ArchivePopup
        sb = self.window.sidebar
        if anchor is None:
            if sb.hidden_mode and not sb.floating:
                sb.peek()
            anchor = sb.archive_btn if sb.isVisible() else self.window.titlebar.menu_btn
        popup = ArchivePopup(self.ctx, self, self.window)
        popup.popup_above(anchor)

    # ---------------------------------------------------------- pin & favourite
    def toggle_pin(self, tab_id: str | None = None) -> None:
        tab = self.ctx.state.tab(tab_id) if tab_id else self.ctx.state.active_tab
        if tab is None:
            return
        pinned = not tab.pinned
        self.ctx.state.set_pinned(tab.id, pinned)
        self.toast("Card pinned. It stays at the start of this space" if pinned else "Card unpinned",
                   "pin" if pinned else "unpin")
        c = self.canvas(tab.space_id)
        if c:
            QTimer.singleShot(0, lambda: c.ensure_visible(tab.id))

    def toggle_favourite(self, tab_id: str | None = None) -> None:
        tab = self.ctx.state.tab(tab_id) if tab_id else self.ctx.state.active_tab
        if tab is None or not tab.url or tab.url.startswith(("about:", "data:")):
            return
        favs = self.ctx.favourites
        fav = favs.get(tab.favourite_id) if tab.favourite_id else None
        fav = fav or favs.find_url(tab.url)
        if fav is not None:
            favs.remove(fav.id)
            tab.favourite_id = ""
            self.toast(f"Removed {fav.label()} from favourites", "star")
            return
        if favs.is_full():
            self.toast("Favourites are full. Remove one to make room", "star")
            return
        fav = favs.add(tab.url, tab.display_title())
        if fav is not None:
            tab.favourite_id = fav.id
            self.ctx.session.mark_dirty()
            hint = "" if not self.window.sidebar.hidden_mode else " (show the sidebar to see it)"
            self.toast(f"Added to favourites above your spaces{hint}", "star_fill")

    def favourite_state(self, fid: str) -> str:
        space = self.ctx.state.active_space
        if space is None:
            return ""
        state = ""
        for t in space.tabs:
            if t.favourite_id == fid:
                if t.id == space.active_tab_id:
                    return "active"
                state = "open"
        return state

    def open_favourite(self, fid: str, force_new: bool = False) -> None:
        fav = self.ctx.favourites.get(fid)
        space = self.ctx.state.active_space
        if fav is None or space is None:
            return
        if not force_new:
            for t in space.tabs:
                if t.favourite_id == fid:
                    self.activate_card(t.id, wake=True, center=True)
                    return
        tab = self.open_url(QUrl(fav.url), "new")
        if tab is not None:
            tab.favourite_id = fid
            self.ctx.session.mark_dirty()

    def show_favourite_menu(self, fid: str, pos: QPoint) -> None:
        fav = self.ctx.favourites.get(fid)
        if fav is None:
            return
        m = QMenu(self.window)
        menu_action(m, "Open", lambda: self.open_favourite(fid), "page")
        menu_action(m, "Open in a new card", lambda: self.open_favourite(fid, force_new=True), "add")
        menu_action(m, "Open in the background", lambda: self.open_url(QUrl(fav.url), "background"), "taskview")
        m.addSeparator()
        menu_action(m, "Rename…", lambda: self._rename_favourite(fid), "edit")
        tab = self.ctx.state.active_tab
        if tab is not None and tab.url.startswith(("http://", "https://")) and tab.url != fav.url:
            menu_action(m, "Use this card's page", lambda: (self.ctx.favourites.update(fid, url=tab.url),
                                                             setattr(tab, "favourite_id", fid)), "link")
        menu_action(m, "Copy address", lambda: QGuiApplication.clipboard().setText(fav.url), "copy")
        m.addSeparator()
        menu_action(m, "Remove from favourites", lambda: self.ctx.favourites.remove(fid), "delete")
        m.exec(pos)

    def _rename_favourite(self, fid: str) -> None:
        fav = self.ctx.favourites.get(fid)
        if fav is None:
            return
        name, ok = QInputDialog.getText(self.window, "Rename favourite", "Name:", QLineEdit.EchoMode.Normal,
                                        fav.label())
        if ok and name.strip():
            self.ctx.favourites.update(fid, title=name.strip())

    def duplicate_tab(self, tab_id: str | None = None) -> None:
        tab = self.ctx.state.tab(tab_id) if tab_id else self.ctx.state.active_tab
        if tab is None:
            return
        ctrl = self.ctx.engine.controller(tab.id)
        space = self.ctx.state.space_of(tab)
        new = self.ctx.state.add_tab(space.id, tab.url, index=space.index_of(tab.id) + 1, width=tab.width,
                                     title=tab.title, history=ctrl.history_bytes() if ctrl else None)
        if new:
            QTimer.singleShot(0, lambda: self.activate_card(new.id))

    def activate_card(self, tab_id: str, modifiers=Qt.KeyboardModifier.NoModifier, wake: bool = False,
                      focus: bool = True, center: bool = False) -> None:
        st = self.ctx.state
        tab = st.tab(tab_id)
        if tab is None:
            return
        space = st.space_of(tab)
        if space.id != st.active_space_id:
            st.set_active_space(space.id)
        mods = modifiers if isinstance(modifiers, Qt.KeyboardModifier) else Qt.KeyboardModifier(modifiers)
        if mods & Qt.KeyboardModifier.ControlModifier:
            st.select_tab(tab_id, "toggle")
            return
        if mods & Qt.KeyboardModifier.ShiftModifier:
            st.select_tab(tab_id, "range")
            return
        st.select_tab(tab_id, "single")
        if wake and tab.sleeping:
            self.ctx.lifecycle.wake(tab_id)
        canvas = self.canvas(space.id)
        if canvas:
            canvas.ensure_visible(tab_id, "center" if center else "nearest")
        if focus:
            card = self.card(tab_id)
            if card:
                card.focus_view()

    def focus_active_card(self) -> None:
        card = self.active_card()
        if card:
            card.focus_view()

    def focus_adjacent(self, delta: int, edge_add: bool = False, wrap: bool = False) -> None:
        """Move focus to the neighbouring card. With ``edge_add`` (Alt+←/→), pressing again at the
        first / last card reveals the "+" and a second press adds a card there."""
        space = self.ctx.state.active_space
        if not space or not space.tabs:
            return
        idx = space.index_of(space.active_tab_id)
        n = len(space.tabs)
        if wrap and idx >= 0:
            nxt = (idx + delta) % n
        else:
            nxt = max(0, min(n - 1, idx + delta))
        if nxt != idx or idx < 0:
            self.activate_card(space.tabs[nxt].id, wake=False)
        elif edge_add:
            c = self.canvas()
            if c is not None:
                c.edge_nudge(-1 if delta < 0 else 1)

    def goto_index(self, n: int) -> None:
        space = self.ctx.state.active_space
        if not space or not space.tabs:
            return
        idx = len(space.tabs) - 1 if n < 0 else min(n, len(space.tabs) - 1)
        self.activate_card(space.tabs[idx].id, center=True)

    def move_card(self, delta: int) -> None:
        tab = self.ctx.state.active_tab
        space = self.ctx.state.active_space
        if not tab or not space:
            return
        self.ctx.state.move_tab(tab.id, space.index_of(tab.id) + delta)
        c = self.canvas()
        if c:
            QTimer.singleShot(0, lambda: c.ensure_visible(tab.id))

    def move_tab_to_space(self, tab_id: str, space_id: str) -> None:
        new = self.ctx.state.move_tab_to_space(tab_id, space_id)
        if new:
            sp = self.ctx.state.space(space_id)
            self.toast(f"Moved to {sp.name} (signed-in state stays isolated per space)", "people")

    # ------------------------------------------------------------- scaling
    def scale_selected(self, frac: float) -> None:
        tabs = self.ctx.state.selected_tabs()
        if not tabs:
            return
        for t in tabs:
            t.update(width=frac)
        c = self.canvas()
        if c:
            c.ensure_visible(tabs[0].id, "left" if len(tabs) > 1 or frac >= 0.999 else "nearest")
        label = "Full width" if frac >= 0.999 else f"{round(frac * 100)}% width"
        if len(tabs) > 1:
            label += f" · {len(tabs)} cards"
        self.toast(label, "columns")

    def toggle_full_width(self, tab_id: str) -> None:
        tab = self.ctx.state.tab(tab_id)
        if tab is None:
            return
        if tab.width >= 0.999:
            tab.update(width=self._prev_width.pop(tab_id, self.ctx.settings.get("canvas.default_width")))
        else:
            self._prev_width[tab_id] = tab.width
            tab.update(width=1.0)
        c = self.canvas(tab.space_id)
        if c:
            c.ensure_visible(tab_id, "left")

    def split(self, n: int) -> None:
        space = self.ctx.state.active_space
        if not space or not space.tabs:
            return
        selected = self.ctx.state.selected_tabs(space)
        if len(selected) == n:
            tabs = selected
        else:
            idx = max(0, space.index_of(space.active_tab_id))
            start = max(0, min(idx, len(space.tabs) - n))
            tabs = space.tabs[start:start + n]
        for t in tabs:
            t.update(width=1.0 / len(tabs))
        c = self.canvas()
        if c and tabs:
            c.ensure_visible(tabs[0].id, "left")
        names = {2: "Split view 50 / 50", 3: "Triple columns 33 / 33 / 33", 4: "Quad columns"}
        self.toast(names.get(len(tabs), f"{len(tabs)} columns"), "columns")

    def select_all_cards(self) -> None:
        self.ctx.state.select_all()
        self.toast("All cards selected. Alt+1 to Alt+9 or Alt+0 resizes them together", "selectall")

    # ---------------------------------------------------------- navigation
    def nav(self, action: str) -> None:
        ctrl = self.ctrl()
        if ctrl is None:
            return
        if ctrl.tab.sleeping and action.startswith("reload"):
            self.ctx.lifecycle.wake(ctrl.tab.id)
            return
        if action == "back":
            ctrl.back()
        elif action == "forward":
            ctrl.forward()
        elif action == "reload":
            ctrl.reload()
        elif action == "hard_reload":
            ctrl.reload(bypass_cache=True)
        elif action == "stop":
            ctrl.stop()
        elif action == "reload_or_stop":
            ctrl.stop() if ctrl.tab.loading else ctrl.reload()

    def zoom(self, direction: int) -> None:
        ctrl = self.ctrl()
        if ctrl is None:
            return
        if direction == 0:
            ctrl.set_zoom(1.0)
        else:
            ctrl.zoom_step(direction)
        self.toast(f"Zoom {round(ctrl.tab.zoom * 100)}%", "zoom_in" if direction >= 0 else "zoom_out")

    def find_in_page(self) -> None:
        card = self.active_card()
        if card:
            card.open_find()

    def toggle_devtools(self) -> None:
        card = self.active_card()
        if card:
            card.toggle_devtools()

    def view_source(self) -> None:
        tab = self.ctx.state.active_tab
        if tab and tab.url:
            self.open_url(QUrl("view-source:" + tab.url), "new", after_tab=tab.id)

    def print_card(self, tab_id: str | None = None) -> None:
        from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
        card = self.card(tab_id) if tab_id else self.active_card()
        if card is None or card.tab.sleeping:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self.window)
        dlg.setWindowTitle("Print page")
        if dlg.exec() != QPrintDialog.DialogCode.Accepted:
            return
        self._printers.append(printer)

        def finished(ok: bool, p=printer, view=card.view):
            try:
                view.printFinished.disconnect(finished)
            except (TypeError, RuntimeError):
                pass
            if p in self._printers:
                self._printers.remove(p)
            self.toast("Sent to printer" if ok else "Printing failed", "print")

        card.view.printFinished.connect(finished)
        card.view.print(printer)

    def save_page(self) -> None:
        ctrl = self.ctrl()
        if ctrl is None or not ctrl.tab.url:
            return
        name = (ctrl.tab.title or "page").strip().replace("/", "_").replace("\\", "_")[:80] + ".html"
        path, flt = QFileDialog.getSaveFileName(self.window, "Save page", f"{self.ctx.downloads.default_directory()}/{name}",
                                                "Web page, complete (*.html);;Single file (*.mhtml);;HTML only (*.html)")
        if not path:
            return
        fmt = QWebEngineDownloadRequest.SavePageFormat
        choice = fmt.MimeHtmlSaveFormat if "mhtml" in flt else (fmt.SingleHtmlSaveFormat if "only" in flt
                                                               else fmt.CompleteHtmlSaveFormat)
        ctrl.page.save(path, choice)

    def save_pdf(self) -> None:
        ctrl = self.ctrl()
        if ctrl is None or not ctrl.tab.url:
            return
        name = (ctrl.tab.title or "page").strip().replace("/", "_").replace("\\", "_")[:80] + ".pdf"
        path, _ = QFileDialog.getSaveFileName(self.window, "Save as PDF",
                                              f"{self.ctx.downloads.default_directory()}/{name}", "PDF (*.pdf)")
        if path:
            ctrl.page.pdfPrintingFinished.connect(
                lambda p, ok: self.toast("PDF saved" if ok else "Could not save PDF", "save"))
            ctrl.page.printToPdf(path)

    def copy_url(self) -> None:
        tab = self.ctx.state.active_tab
        if tab and tab.url:
            QGuiApplication.clipboard().setText(tab.url)
            self.toast("Address copied", "link")

    def copy_screenshot(self, tab_id: str | None = None) -> None:
        card = self.card(tab_id) if tab_id else self.active_card()
        if card is None:
            return
        pm = card.view.grab() if not card.tab.sleeping else card.snapshot.grab()
        QGuiApplication.clipboard().setPixmap(pm)
        self.toast("Card screenshot copied to clipboard", "crop")

    def open_external(self) -> None:
        tab = self.ctx.state.active_tab
        if tab and tab.url.startswith(("http://", "https://")):
            QDesktopServices.openUrl(QUrl(tab.url))

    def toggle_mute(self, tab_id: str | None = None) -> None:
        ctrl = self.ctrl(tab_id)
        if ctrl:
            ctrl.toggle_mute()

    # ------------------------------------------------------------- sleep
    def sleep_tab(self, tab_id: str | None = None) -> None:
        tab = self.ctx.state.tab(tab_id) if tab_id else self.ctx.state.active_tab
        if tab is None:
            return
        if tab.sleeping:
            self.toast("Card is already asleep", "moon")
            return
        self.ctx.lifecycle.try_sleep(tab, manual=True)

    def wake_tab(self, tab_id: str) -> None:
        self.ctx.lifecycle.wake(tab_id)
        self.activate_card(tab_id)

    def on_sleep_blocked(self, tab_id: str, reason: str) -> None:
        tab = self.ctx.state.tab(tab_id)
        name = tab.display_title() if tab else "Card"
        self.toast(f"“{name[:40]}” stays awake: {reason}", "moon")

    # ------------------------------------------------------------- spaces
    def switch_space(self, delta: int) -> None:
        self.ctx.state.cycle_space(delta)

    def select_space(self, space_id: str) -> None:
        self.ctx.state.set_active_space(space_id)

    def new_space(self, incognito: bool = False) -> None:
        if incognito:
            n = sum(1 for s in self.ctx.state.spaces if s.incognito) + 1
            self.ctx.state.add_space(f"Incognito {n}" if n > 1 else "Incognito", "🕶️", "#6c6f7f", incognito=True)
            self.toast("Incognito space. Nothing from it is saved to disk", "incognito")
            QTimer.singleShot(0, lambda: self.open_lazy_toolbar("new"))
            return
        from jbrowser.ui.dialogs.space import SpaceDialog
        dlg = SpaceDialog(self.ctx, None, self.window)
        if dlg.exec():
            name, icon_text, color, incog = dlg.values()
            self.ctx.state.add_space(name, icon_text, color, incognito=incog)
            QTimer.singleShot(0, lambda: self.open_lazy_toolbar("new"))

    def edit_space(self, space_id: str | None = None) -> None:
        space = self.ctx.state.space(space_id) if space_id else self.ctx.state.active_space
        if space is None:
            return
        from jbrowser.ui.dialogs.space import SpaceDialog
        dlg = SpaceDialog(self.ctx, space, self.window)
        if dlg.exec():
            name, icon_text, color, _incog = dlg.values()
            self.ctx.state.update_space(space.id, name=name, icon=icon_text, color=color)

    def delete_space(self, space_id: str | None = None) -> None:
        space = self.ctx.state.space(space_id) if space_id else self.ctx.state.active_space
        if space is None:
            return
        if len(self.ctx.state.spaces) <= 1:
            self.toast("You need at least one space", "info")
            return
        if space.incognito:
            text = f"Close “{space.name}”? All of its cards and in-memory data will be discarded."
        else:
            text = (f"Delete “{space.name}”?\n\nIts {len(space.tabs)} card(s), cookies, logins, cache and site data "
                    f"will be permanently removed from this device.")
        if QMessageBox.question(self.window, "Delete space", text) != QMessageBox.StandardButton.Yes:
            return
        self.ctx.state.remove_space(space.id)

    def set_space_proxy(self, space_id: str | None = None) -> None:
        from jbrowser.ui.dialogs.network import ProxyDialog
        space = self.ctx.state.space(space_id) if space_id else self.ctx.state.active_space
        if space:
            ProxyDialog(self.ctx, space, self.window).exec()

    # --------------------------------------------------------------- menus
    def show_card_menu(self, tab_id: str, pos: QPoint) -> None:
        st = self.ctx.state
        tab = st.tab(tab_id)
        if tab is None:
            return
        ctrl = self.ctx.engine.controller(tab_id)
        card = self.card(tab_id)
        m = QMenu(self.window)
        menu_action(m, "Reload", lambda: (self.activate_card(tab_id), self.nav("reload")), "refresh", shortcut="F5")
        menu_action(m, "Duplicate card", lambda: self.duplicate_tab(tab_id), "copy")
        menu_action(m, "Copy address", lambda: QGuiApplication.clipboard().setText(tab.url), "link")
        menu_action(m, "Copy link without trackers", lambda: self.copy_clean_link(tab_id), "link")
        bm = self.ctx.bookmarks.find_url(tab.url)
        menu_action(m, "Remove bookmark" if bm else "Bookmark page", lambda: self.toggle_bookmark(tab_id),
                    "star_fill" if bm else "star")
        menu_action(m, "Unmute card" if tab.muted else "Mute card", lambda: self.toggle_mute(tab_id),
                    "volume" if tab.muted else "mute")
        menu_action(m, "Unpin card" if tab.pinned else "Pin card", lambda: self.toggle_pin(tab_id),
                    "unpin" if tab.pinned else "pin")
        fav = (self.ctx.favourites.get(tab.favourite_id) if tab.favourite_id else None) or \
            self.ctx.favourites.find_url(tab.url)
        menu_action(m, "Remove from favourites" if fav else "Add to favourites", lambda: self.toggle_favourite(tab_id),
                    "star_fill" if fav else "star")
        m.addSeparator()
        widths = submenu(m, "Card width", "columns")
        for frac, label in WIDTH_PRESETS:
            menu_action(widths, label, lambda f=frac: (st.set_active_tab(tab_id), self.scale_selected(f)),
                        checkable=True, checked=abs(tab.width - frac) < 0.01)
        if tab.sleeping:
            menu_action(m, "Wake card", lambda: self.wake_tab(tab_id), "sun")
        else:
            menu_action(m, "Put card to sleep", lambda: self.sleep_tab(tab_id), "moon")
        others = [sp for sp in st.spaces if sp.id != tab.space_id]
        if others:
            mv = submenu(m, "Move to space", "people")
            for sp in others:
                menu_action(mv, f"{sp.icon}  {sp.name}", lambda sid=sp.id: self.move_tab_to_space(tab_id, sid))
        m.addSeparator()
        if card is not None and not tab.sleeping:
            menu_action(m, "Find in page", lambda: card.open_find(), "search", shortcut="Ctrl+F")
            menu_action(m, "Developer tools", lambda: card.toggle_devtools(), "code", shortcut="F12")
        host = QUrl(tab.url).host()
        if host:
            menu_action(m, "Site information", lambda: self.show_site_info(tab_id, pos), "info")
        menu_action(m, "Clear this site's data", lambda: self.clear_site_data(tab_id), "clear")
        if host:
            menu_action(m, "Forget this site…", lambda: self.forget_site(host), "delete")
        if ctrl is not None and ctrl.credentials():
            menu_action(m, "Fill saved password", lambda: self.show_password_menu(tab_id, pos), "key")
        m.addSeparator()
        menu_action(m, "Close other cards", lambda: self.close_others(tab_id), "clear")
        menu_action(m, "Close card", lambda: self.close_tab(tab_id), "close", shortcut="Ctrl+W")
        m.exec(pos)

    def show_space_menu(self, space_id: str, pos: QPoint) -> None:
        space = self.ctx.state.space(space_id)
        if space is None:
            return
        m = QMenu(self.window)
        menu_action(m, "Switch to space", lambda: self.select_space(space_id), "switch")
        menu_action(m, "Edit name, icon & color…", lambda: self.edit_space(space_id), "edit")
        menu_action(m, f"Proxy for this space… ({describe_proxy(space.proxy) if space.proxy else 'inherit'})",
                    lambda: self.set_space_proxy(space_id), "vpn")
        menu_action(m, "User scripts & styles…", lambda: self.open_dialog("userscripts"), "code")
        m.addSeparator()
        menu_action(m, "Wake all cards", lambda: self.ctx.lifecycle.wake_all(space_id), "sun")
        menu_action(m, "Clear cache for this space", lambda: (self.ctx.profiles.clear_cache(space_id),
                                                              self.toast("Cache cleared", "clear")), "clear")
        menu_action(m, "Delete cookies for this space",
                    lambda: (self.ctx.cookies.delete_all(space_id), self.toast("Cookies deleted", "clear")), "delete")
        m.addSeparator()
        idx = self.ctx.state.spaces.index(space)
        menu_action(m, "Move up", lambda: self.ctx.state.move_space(space_id, idx - 1), "chev_up", enabled=idx > 0)
        menu_action(m, "Move down", lambda: self.ctx.state.move_space(space_id, idx + 1), "chev_down",
                    enabled=idx < len(self.ctx.state.spaces) - 1)
        menu_action(m, "Close incognito space" if space.incognito else "Delete space…",
                    lambda: self.delete_space(space_id), "delete")
        m.exec(pos)

    def show_spaces_menu(self, pos: QPoint) -> None:
        m = QMenu(self.window)
        for i, sp in enumerate(self.ctx.state.spaces):
            menu_action(m, f"{sp.icon}  {sp.name}" + ("  (incognito)" if sp.incognito else ""),
                        lambda sid=sp.id: self.select_space(sid), checkable=True,
                        checked=sp.id == self.ctx.state.active_space_id)
        m.addSeparator()
        menu_action(m, "New space…", lambda: self.new_space(False), "add", shortcut="Ctrl+N")
        menu_action(m, "New incognito space", lambda: self.new_space(True), "incognito", shortcut="Ctrl+Shift+N")
        m.exec(pos)

    def show_layout_menu(self, pos: QPoint) -> None:
        m = QMenu(self.window)
        n_sel = len(self.ctx.state.selected_tabs())
        header = menu_action(m, f"Scale {'selected cards' if n_sel > 1 else 'card'}", None, "columns")
        header.setEnabled(False)
        for n in range(1, 10):
            menu_action(m, f"{n * 10}%", lambda f=n / 10: self.scale_selected(f), shortcut=f"Alt+{n}")
        menu_action(m, "100% (full width)", lambda: self.scale_selected(1.0), shortcut="Alt+0")
        m.addSeparator()
        menu_action(m, "Split view 50 / 50", lambda: self.split(2), "columns", shortcut="Alt+Shift+D")
        menu_action(m, "Triple columns 33 / 33 / 33", lambda: self.split(3), "tiles", shortcut="Alt+Shift+T")
        menu_action(m, "Quad columns 25% × 4", lambda: self.split(4), "grid", shortcut="Alt+Shift+Q")
        menu_action(m, "Focus view 80%", lambda: self.scale_selected(0.8), "fullscreen", shortcut="Alt+8")
        m.addSeparator()
        menu_action(m, "Select all cards", self.select_all_cards, "selectall", shortcut="Ctrl+Shift+A")
        menu_action(m, "Show canvas overview strip", lambda: self.ctx.settings.toggle("canvas.show_minimap"),
                    checkable=True, checked=bool(self.ctx.settings.get("canvas.show_minimap")))
        m.exec(pos)

    def show_shield_menu(self, tab_id: str | None, pos: QPoint) -> None:
        tab = self.ctx.state.tab(tab_id) if tab_id else self.ctx.state.active_tab
        m = QMenu(self.window)
        s = self.ctx.settings
        total = self.ctx.stats.get("blocked", 0)
        if tab is not None and QUrl(tab.url).host():
            host = strip_www(QUrl(tab.url).host())
            protected = not self.ctx.privacy.is_allowlisted(host)
            info = menu_action(m, f"{tab.blocked} tracker(s) blocked on {host}", None, "shield")
            info.setEnabled(False)
            menu_action(m, f"Protection for {host}", lambda: (self.ctx.privacy.set_site_protection(host, not protected),
                                                             self.toast(f"Protection {'off' if protected else 'on'} "
                                                                        f"for {host}. Reload to apply.", "shield")),
                        checkable=True, checked=protected)
            m.addSeparator()
        menu_action(m, "Block trackers, ads, miners & telemetry", lambda: s.toggle("privacy.block_trackers"),
                    checkable=True, checked=bool(s.get("privacy.block_trackers")))
        menu_action(m, "Block third-party cookies", lambda: s.toggle("privacy.block_third_party_cookies"),
                    checkable=True, checked=bool(s.get("privacy.block_third_party_cookies")))
        menu_action(m, "Phishing and malware protection", lambda: s.toggle("privacy.threat_protection"),
                    checkable=True, checked=bool(s.get("privacy.threat_protection")))
        menu_action(m, "Fingerprinting protection", lambda: s.toggle("privacy.fingerprint_protection"),
                    checkable=True, checked=bool(s.get("privacy.fingerprint_protection")))
        menu_action(m, "Remove tracking codes from links", lambda: s.toggle("privacy.strip_tracking"),
                    checkable=True, checked=bool(s.get("privacy.strip_tracking")))
        menu_action(m, "Send Global Privacy Control (GPC)", lambda: s.toggle("privacy.gpc"), checkable=True,
                    checked=bool(s.get("privacy.gpc")))
        menu_action(m, "Send Do Not Track (DNT)", lambda: s.toggle("privacy.dnt"), checkable=True,
                    checked=bool(s.get("privacy.dnt")))
        m.addSeparator()
        d = menu_action(m, f"{total:,} requests blocked this session · {len(self.ctx.privacy.blocklist):,} rules",
                        None, "info")
        d.setEnabled(False)
        menu_action(m, "Privacy settings…", lambda: self.open_settings("privacy"), "settings")
        m.exec(pos)

    def show_password_menu(self, tab_id: str, pos: QPoint) -> None:
        ctrl = self.ctx.engine.controller(tab_id)
        if ctrl is None:
            return
        m = QMenu(self.window)
        creds = ctrl.credentials()
        if not creds:
            if self.ctx.vault.mode == "master" and self.ctx.vault.is_locked:
                menu_action(m, "Unlock vault…", self.unlock_vault, "lock")
            else:
                a = menu_action(m, "No saved passwords for this site", None, "key")
                a.setEnabled(False)
        for c in creds:
            menu_action(m, f"Fill {c.username or '(no username)'}", lambda cc=c: ctrl.fill(cc), "key")
        m.addSeparator()
        menu_action(m, "Manage passwords…", lambda: self.open_dialog("passwords"), "settings")
        m.exec(pos)

    def show_main_menu(self, pos: QPoint) -> None:
        m = QMenu(self.window)
        run = self.ctx.commands.run
        menu_action(m, "New card", lambda: run("card.new"), "add", shortcut="Ctrl+T")
        menu_action(m, "New space…", lambda: run("space.new"), "people", shortcut="Ctrl+N")
        menu_action(m, "New incognito space", lambda: run("space.new_incognito"), "incognito",
                    shortcut="Ctrl+Shift+N")
        menu_action(m, "Reopen closed card", lambda: run("card.reopen"), "history", shortcut="Ctrl+Shift+T")
        m.addSeparator()
        menu_action(m, "Gallery", lambda: run("gallery.toggle"), "gallery", shortcut="Ctrl+Shift+G")
        menu_action(m, "Archive", lambda: run("archive.show"), "archive", shortcut="Ctrl+Shift+Y")
        menu_action(m, "History", lambda: run("history.show"), "history", shortcut="Ctrl+H")
        menu_action(m, "Bookmarks", lambda: run("bookmarks.show"), "bookmarks", shortcut="Ctrl+Shift+O")
        menu_action(m, "Downloads", lambda: run("downloads.show"), "download", shortcut="Ctrl+J")
        menu_action(m, "Passwords", lambda: run("passwords.show"), "key")
        m.addSeparator()
        page = submenu(m, "Page", "page")
        menu_action(page, "Find in page", lambda: run("page.find"), "search", shortcut="Ctrl+F")
        menu_action(page, "Zoom in", lambda: run("page.zoom_in"), "zoom_in", shortcut="Ctrl+=")
        menu_action(page, "Zoom out", lambda: run("page.zoom_out"), "zoom_out", shortcut="Ctrl+-")
        menu_action(page, "Reset zoom", lambda: run("page.zoom_reset"), shortcut="Ctrl+0")
        menu_action(page, "Print…", lambda: run("page.print"), "print", shortcut="Ctrl+P")
        menu_action(page, "Save page as…", lambda: run("page.save"), "save", shortcut="Ctrl+S")
        menu_action(page, "Save as PDF…", lambda: run("page.pdf"), "save")
        menu_action(page, "View source", lambda: run("page.view_source"), "code", shortcut="Ctrl+U")
        menu_action(page, "Developer tools", lambda: run("page.devtools"), "code", shortcut="F12")
        menu_action(page, "Open in default browser", lambda: run("card.open_external"), "newwindow")
        privacy = submenu(m, "Privacy & data", "shield")
        menu_action(privacy, "Site information", lambda: run("privacy.site_info"), "info")
        menu_action(privacy, "Clear browsing data…", lambda: run("privacy.clear_data"), "clear",
                    shortcut="Ctrl+Shift+Del")
        menu_action(privacy, "Cookies…", lambda: run("cookies.show"), "fingerprint")
        menu_action(privacy, "Site permissions…", lambda: run("permissions.show"), "permissions")
        menu_action(privacy, "User scripts & styles…", lambda: run("userscripts.show"), "code")
        privacy.addSeparator()
        menu_action(privacy, "Privacy and security settings", lambda: self.open_settings("privacy"), "shield")
        net = submenu(m, "Network", "network")
        for mode, info in DNS_MODES.items():
            menu_action(net, f"DNS: {info['label']}", lambda mm=mode: self.set_dns(mm), checkable=True,
                        checked=self.ctx.settings.get("network.dns_mode") == mode)
        net.addSeparator()
        menu_action(net, f"Proxy: {self.ctx.proxy.description}", lambda: run("proxy.settings"), "vpn")
        menu_action(net, "Localhost developer mapping…", lambda: run("dev.hosts"), "developer")
        perf = submenu(m, "Memory saver", "speed")
        for pid, (label, _mins) in SLEEP_PRESETS.items():
            menu_action(perf, label, lambda p=pid: self.set_sleep_preset(p), checkable=True,
                        checked=self.ctx.settings.get("performance.sleep_preset") == pid)
        perf.addSeparator()
        menu_action(perf, "Throttle cards out of view", lambda: self.ctx.settings.toggle("performance.throttle"),
                    checkable=True, checked=bool(self.ctx.settings.get("performance.throttle")))
        menu_action(perf, "Sleep inactive cards now", lambda: run("card.sleep_inactive"), "moon")
        m.addSeparator()
        menu_action(m, "Sidebar", lambda: run("view.toggle_sidebar"), checkable=True,
                    checked=not self.ctx.settings.get("appearance.sidebar_collapsed"), shortcut="Ctrl+B")
        menu_action(m, "Bookmarks bar", lambda: run("view.toggle_favorites"), checkable=True,
                    checked=bool(self.ctx.settings.get("appearance.favorites_bar")), shortcut="Ctrl+Shift+B")
        menu_action(m, "Home button", lambda: run("view.toggle_home"), checkable=True,
                    checked=bool(self.ctx.settings.get("toolbar.home_button")))
        menu_action(m, "Keyboard shortcuts", lambda: run("view.hotkeys"), "keyboard", shortcut="Ctrl+/")
        menu_action(m, "Settings", lambda: run("settings.show"), "settings", shortcut="Ctrl+,")
        menu_action(m, "About JBrowser", lambda: run("app.about"), "info")
        m.addSeparator()
        menu_action(m, "Exit", lambda: run("app.quit"), "power", shortcut="Ctrl+Shift+Q")
        m.exec(pos)

    # ------------------------------------------------------------- toggles
    def toggle_sidebar(self) -> None:
        self.set_sidebar_hidden(not self.ctx.settings.get("appearance.sidebar_collapsed"))

    def set_sidebar_hidden(self, hidden: bool) -> None:
        self.ctx.settings.set("appearance.sidebar_collapsed", hidden)
        self.window.sidebar.set_collapsed(hidden)
        if hidden:
            self.toast("Sidebar hidden. Point at the left edge to peek, or press Ctrl+B to bring it back", "sidebar")

    def show_ribbon_menu(self, pos: QPoint) -> None:
        s = self.ctx.settings
        m = QMenu(self.window)
        hidden = bool(s.get("appearance.sidebar_collapsed"))
        menu_action(m, "Show sidebar" if hidden else "Hide sidebar", lambda: self.set_sidebar_hidden(not hidden),
                    "sidebar", shortcut="Ctrl+B")
        menu_action(m, "Bookmarks bar", self.toggle_favorites_bar, checkable=True,
                    checked=bool(s.get("appearance.favorites_bar")), shortcut="Ctrl+Shift+B")
        menu_action(m, "Home button", lambda: s.toggle("toolbar.home_button"), checkable=True,
                    checked=bool(s.get("toolbar.home_button")))
        m.addSeparator()
        menu_action(m, "Ribbon and appearance settings…", lambda: self.open_settings("appearance"), "settings")
        m.exec(pos)

    def show_sidebar_menu(self, pos: QPoint) -> None:
        m = QMenu(self.window)
        menu_action(m, "Hide sidebar", lambda: self.set_sidebar_hidden(True), "closepane", shortcut="Ctrl+B")
        m.addSeparator()
        menu_action(m, "New card", lambda: self.open_lazy_toolbar("new"), "add", shortcut="Ctrl+T")
        menu_action(m, "New space…", lambda: self.new_space(False), "people", shortcut="Ctrl+N")
        menu_action(m, "New incognito space", lambda: self.new_space(True), "incognito", shortcut="Ctrl+Shift+N")
        menu_action(m, "Gallery of all spaces", lambda: self.toggle_gallery(True), "layers")
        menu_action(m, "Archive", lambda: self.show_archive(), "archive", shortcut="Ctrl+Shift+Y")
        m.addSeparator()
        menu_action(m, "Settings", lambda: self.open_settings(), "settings", shortcut="Ctrl+,")
        m.exec(pos)

    # ----------------------------------------------------------------- home
    def go_home(self, new_card: bool = False) -> None:
        s = self.ctx.settings
        url = (s.get("toolbar.home_url") or "").strip()
        if s.get("toolbar.home_mode") == "url" and url:
            target = "new" if new_card or self.ctx.state.active_tab is None else "current"
            self.open_url(url, target)
        else:
            self.open_lazy_toolbar("new")

    def show_home_menu(self, pos: QPoint) -> None:
        s = self.ctx.settings
        m = QMenu(self.window)
        url = (s.get("toolbar.home_url") or "").strip()
        mode = s.get("toolbar.home_mode")
        menu_action(m, "Home opens the Lazy Toolbar", lambda: s.set("toolbar.home_mode", "lazy"), checkable=True,
                    checked=mode != "url" or not url)
        menu_action(m, f"Home opens {pretty_url(url, keep_path=False)}" if url else "Home opens a web page…",
                    lambda: s.set("toolbar.home_mode", "url") if url else self.open_settings("appearance"),
                    checkable=True, checked=mode == "url" and bool(url))
        tab = self.ctx.state.active_tab
        if tab is not None and tab.url.startswith(("http://", "https://")):
            menu_action(m, "Use this card's page as home",
                        lambda: (s.set("toolbar.home_url", tab.url), s.set("toolbar.home_mode", "url"),
                                 self.toast("Home page set", "home")), "home")
        m.addSeparator()
        menu_action(m, "Home button settings…", lambda: self.open_settings("appearance"), "settings")
        menu_action(m, "Hide Home button", lambda: s.set("toolbar.home_button", False), "close")
        m.exec(pos)

    def toggle_favorites_bar(self) -> None:
        shown = self.ctx.settings.toggle("appearance.favorites_bar")
        self.window.favbar.set_shown(shown)

    def toggle_animations(self) -> None:
        on = self.ctx.settings.toggle("appearance.animations")
        self.toast("Fluid animations on" if on else "Fluid animations off. Transitions are now instant", "lightning")

    def set_theme(self, mode: str) -> None:
        self.ctx.settings.set("appearance.theme", mode)

    def set_material(self, material: str) -> None:
        self.ctx.settings.set("appearance.material", material)

    def toggle_maximize(self) -> None:
        w = self.window
        w.showNormal() if w.isMaximized() else w.showMaximized()

    def toggle_window_fullscreen(self) -> None:
        w = self.window
        if w.isFullScreen():
            w.showMaximized() if w.was_maximized else w.showNormal()
        else:
            w.was_maximized = w.isMaximized()
            w.showFullScreen()

    def set_dns(self, mode: str) -> None:
        self.ctx.settings.set("network.dns_mode", mode)
        ok = self.ctx.dns.current == mode
        self.toast(f"DNS: {DNS_MODES[mode]['label']}" + ("" if ok else " (unavailable in this Qt build)"), "network")

    def toggle_proxy(self) -> None:
        desc = self.ctx.proxy.toggle_global()
        self.toast(f"Proxy: {desc}", "vpn")

    def set_sleep_preset(self, preset: str) -> None:
        self.ctx.settings.set("performance.sleep_preset", preset)
        self.toast(f"Memory saver: {SLEEP_PRESETS[preset][0]}", "speed")

    # ---------------------------------------------------------------- data
    def clear_site_data(self, tab_id: str | None = None) -> None:
        ctrl = self.ctrl(tab_id)
        if ctrl is None or not ctrl.tab.url:
            return
        host = QUrl(ctrl.tab.url).host()
        if not host:
            self.toast("This page has no site data to clear", "info")
            return
        if QMessageBox.question(self.window, "Clear site data",
                                f"Delete cookies, storage, caches and service workers for {host} in this space?") \
                != QMessageBox.StandardButton.Yes:
            return
        ctrl.clear_site_storage()
        QTimer.singleShot(400, lambda: ctrl.reload(bypass_cache=True))
        self.toast(f"Cleared data for {host}", "clear")

    def show_site_info_anchored(self) -> None:
        """Site information from the keyboard / palette: anchor under the address pill."""
        pill = self.window.titlebar.pill
        self.show_site_info(None, pill.mapToGlobal(QPoint(8, pill.height() + 4)))

    def forget_current_site(self) -> None:
        tab = self.ctx.state.active_tab
        if tab is not None and QUrl(tab.url).host():
            self.forget_site(QUrl(tab.url).host())

    def show_site_info(self, tab_id: str | None, pos: QPoint) -> None:
        from jbrowser.ui.site_info import SiteInfoPopup
        tab = self.ctx.state.tab(tab_id) if tab_id else self.ctx.state.active_tab
        if tab is None or not tab.url:
            return
        SiteInfoPopup(self.ctx, self, tab, self.window).popup_at(pos)

    def forget_site(self, host: str) -> None:
        host = strip_www(host)
        if not host:
            return
        if QMessageBox.question(
                self.window, "Forget this site",
                f"Remove everything JBrowser knows about {host}?\n\nThis deletes its history, cookies, "
                "permissions and saved zoom in every space, clears its storage in open cards and closes those "
                "cards. Saved passwords are kept.") != QMessageBox.StandardButton.Yes:
            return
        removed = self.ctx.forget_site(host)
        for tab in list(self.ctx.state.all_tabs()):
            th = strip_www(QUrl(tab.url).host().lower())
            if th == host or th.endswith("." + host):
                self.close_tab(tab.id, remember=False)
        self.toast(f"Forgot {host}: {removed['history']} history entries and {removed['cookies']} cookies removed",
                   "clear")

    def copy_clean_link(self, tab_id: str | None = None) -> None:
        from jbrowser.services.privacy import strip_tracking
        tab = self.ctx.state.tab(tab_id) if tab_id else self.ctx.state.active_tab
        if tab is None or not tab.url:
            return
        clean, removed = strip_tracking(QUrl(tab.url))
        QGuiApplication.clipboard().setText(clean.toString())
        self.toast(f"Link copied ({removed} tracking parameter{'s' if removed != 1 else ''} removed)"
                   if removed else "Link copied", "link")

    def confirm_dangerous_download(self, name: str, host: str, insecure: bool) -> bool:
        box = QMessageBox(self.window)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Keep this file?")
        box.setText(f"“{name}” is a program or script.")
        detail = (f"Files like this can install software or change your computer. Only keep it if you trust "
                  f"{host or 'its source'} and you were expecting it.")
        if insecure:
            detail += "\n\nIt is also being downloaded over an insecure (HTTP) connection, so it could have been " \
                      "tampered with on the way."
        box.setInformativeText(detail)
        keep = box.addButton("Keep file", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Discard", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(discard)
        box.exec()
        return box.clickedButton() is keep

    def reset_settings(self) -> None:
        if QMessageBox.question(self.window, "Reset settings",
                                "Put every setting back to its default? Your spaces, cards, history, bookmarks "
                                "and passwords are kept.") != QMessageBox.StandardButton.Yes:
            return
        self.ctx.settings.reset_to_defaults()
        self.window.favbar.set_shown(bool(self.ctx.settings.get("appearance.favorites_bar")))
        self.window.sidebar.set_collapsed(False)
        self.toast("All settings restored to their defaults", "sync")

    def factory_reset(self) -> None:
        box = QMessageBox(self.window)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Factory reset")
        box.setText("Erase all JBrowser data and start fresh?")
        box.setInformativeText(
            "This permanently deletes every space, card, cookie, login session, cached file, history entry, "
            "bookmark, saved password, download record, user script and setting on this computer. "
            "Files you downloaded stay where they are.\n\nJBrowser will close and restart.")
        erase = box.addButton("Erase everything and restart", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is not erase:
            return
        try:
            self.ctx.paths.reset_marker.write_text("reset", "utf-8")
        except OSError as exc:
            QMessageBox.warning(self.window, "Factory reset", f"Could not schedule the reset: {exc}")
            return
        self.restart()

    def restart(self) -> None:
        self.ctx.restart_requested = True
        self.window.close()

    def toggle_bookmark(self, tab_id: str | None = None) -> None:
        tab = self.ctx.state.tab(tab_id) if tab_id else self.ctx.state.active_tab
        if tab is None or not tab.url:
            return
        added = self.ctx.bookmarks.toggle(tab.display_title(), tab.url)
        self.toast("Bookmarked" if added else "Bookmark removed", "star_fill" if added else "star")

    def edit_bookmark(self, bid: str) -> None:
        from jbrowser.ui.dialogs.bookmarks import BookmarkEditDialog
        BookmarkEditDialog(self.ctx, bid, self.window).exec()

    def fill_password(self, cred) -> None:
        ctrl = self.ctrl()
        if ctrl:
            ctrl.fill(cred)

    def copy_secret(self, secret: str, message: str) -> None:
        cb = QGuiApplication.clipboard()
        cb.setText(secret)
        self.toast(message, "copy")

        def clear():
            if cb.text() == secret:
                cb.clear()
        QTimer.singleShot(30000, clear)

    def unlock_vault(self) -> bool:
        vault = self.ctx.vault
        if not vault.is_locked:
            return True
        if vault.mode == "dpapi":
            return vault.ensure_unlocked()
        from jbrowser.ui.dialogs.passwords import ask_master_password
        return ask_master_password(self.ctx, self.window)

    # ------------------------------------------------------------- dialogs
    def toggle_gallery(self, all_spaces: bool | None = None) -> None:
        """Open or close the Gallery (``all_spaces`` forces the scope when opening)."""
        if getattr(self.window, "_onboarding", None) is not None:
            return
        if self.window.lazy.isVisible():
            self.window.lazy.close_overlay()
        self.window.gallery.toggle(all_spaces)

    def open_lazy_toolbar(self, mode: str = "new", text: str = "", insert_at: int | None = None) -> None:
        if getattr(self.window, "_onboarding", None) is not None:
            return                      # the welcome screen owns the window until it finishes
        self.window.lazy.open(mode, text, insert_at)

    def _live_dialog(self, name: str):
        dlg = self._dialogs.get(name)
        if dlg is None:
            return None
        try:
            dlg.isVisible()
        except RuntimeError:      # already deleted (tool windows delete themselves on close)
            self._dialogs.pop(name, None)
            return None
        return dlg

    def _register_dialog(self, name: str, dlg) -> None:
        self._dialogs[name] = dlg
        dlg.destroyed.connect(lambda *_a, n=name, d=dlg: self._dialogs.pop(n, None)
                              if self._dialogs.get(n) is d else None)

    def open_settings(self, page: str = "general") -> None:
        from jbrowser.ui.dialogs.settings import SettingsWindow
        dlg = self._live_dialog("settings")
        if dlg is None:
            dlg = SettingsWindow(self.ctx, self, self.window)
            self._register_dialog("settings", dlg)
        dlg.show_page(page)
        dlg.showNormal() if dlg.isMinimized() else dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def open_dialog(self, name: str) -> None:
        if name in ("clear_data", "about"):
            self.open_settings("clear" if name == "clear_data" else "about")
            return
        existing = self._live_dialog(name)
        if existing is not None:
            existing.showNormal() if existing.isMinimized() else existing.show()
            existing.raise_()
            existing.activateWindow()
            return
        if name == "history":
            from jbrowser.ui.dialogs.history import HistoryDialog as D
        elif name == "bookmarks":
            from jbrowser.ui.dialogs.bookmarks import BookmarksDialog as D
        elif name == "downloads":
            from jbrowser.ui.dialogs.downloads import DownloadsDialog as D
        elif name == "passwords":
            from jbrowser.ui.dialogs.passwords import PasswordsDialog as D
        elif name == "cookies":
            from jbrowser.ui.dialogs.site_data import CookiesDialog as D
        elif name == "permissions":
            from jbrowser.ui.dialogs.site_data import PermissionsDialog as D
        elif name == "userscripts":
            from jbrowser.ui.dialogs.userscripts import UserScriptsDialog as D
        elif name == "proxy":
            from jbrowser.ui.dialogs.network import ProxyDialog
            ProxyDialog(self.ctx, None, self.window).exec()
            return
        elif name == "devhosts":
            from jbrowser.ui.dialogs.network import DevHostsDialog as D
        else:
            return
        dlg = D(self.ctx, self, self.window)
        self._register_dialog(name, dlg)
        dlg.show()

    # -------------------------------------------------------------- updates
    def show_update_dialog(self) -> None:
        from jbrowser.ui.dialogs.update import UpdateDialog
        dlg = self._live_dialog("update")
        if dlg is None:
            dlg = UpdateDialog(self.ctx, self, self.window)
            self._register_dialog("update", dlg)
            dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def check_for_updates(self) -> None:
        """Manual check: report the result instead of staying quiet."""
        up = self.ctx.updater
        if up.state in ("downloading", "ready"):
            self.show_update_dialog()        # an update is already on its way: show its progress
            return
        if up.state == "checking":
            return                           # the running check will report itself

        def done(state: str) -> None:
            if state == "checking":
                return
            try:
                up.stateChanged.disconnect(done)
            except (TypeError, RuntimeError):
                pass
            if state == "available":
                self.show_update_dialog()
            else:
                self.toast(up.message, "sync" if state == "uptodate" else "warning")
        up.stateChanged.connect(done)
        self.toast("Checking for updates…", "sync")
        up.check(manual=True)

    def on_update_available(self, info) -> None:
        self.toast(f"JBrowser {info.version} is available. Click Update on the ribbon to see what's new", "download")

    def open_hotkeys(self) -> None:
        self.window.hotkeys.open_sheet()

    def choose_desktop_media(self, request) -> None:
        from jbrowser.ui.dialogs.media import DesktopMediaDialog
        DesktopMediaDialog(request, self.window).exec()

    # ---------------------------------------------------------- fullscreen
    def handle_fullscreen(self, card: "WebCard", request) -> None:
        if request.toggleOn():
            if self._fs_card is not None and self._fs_card is not card:
                request.reject()
                return
            request.accept()
            self._fs_card = card
            self.window.enter_immersive(card)
        else:
            request.accept()
            if self._fs_card is card:
                self._fs_card = None
                self.window.exit_immersive()

    def open_localhost(self, port: int) -> None:
        self.open_url(QUrl(f"http://localhost:{port}/"), "new")

    def about_ports(self) -> list[tuple[int, str]]:
        return DEV_PORTS
