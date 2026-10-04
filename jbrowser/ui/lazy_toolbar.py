"""The Lazy Toolbar: a centred command overlay that replaces new-tab pages and the omnibox.

Type a URL, a search, a keyword search (``yt lofi``), or fuzzy-find open cards, bookmarks,
history, saved passwords and every browser command. Prefixes narrow the scope:
``>`` commands · ``@`` cards · ``*`` bookmarks · ``#`` history · ``$`` passwords.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from PyQt6.QtCore import QAbstractListModel, QEvent, QModelIndex, QRect, QRectF, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QFont, QFontMetrics, QGuiApplication, QIcon, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QLabel, QLineEdit, QListView, QStyle,
                             QStyledItemDelegate, QVBoxLayout, QWidget)

from jbrowser.core.fuzzy import best_match, fuzzy_match
from jbrowser.core.urls import looks_like_url, pretty_url, strip_www, to_url
from jbrowser.ui.icons import draw_emoji, draw_glyph
from jbrowser.ui.theme import theme
from jbrowser.ui.widgets import Overlay

if TYPE_CHECKING:
    from jbrowser.context import AppContext
    from jbrowser.ui.controller import BrowserController

ROW_H = 48
HEADER_H = 26
MAX_VISIBLE = 10
PREFIXES = {">": "command", "@": "card", "*": "bookmark", "#": "history", "$": "password"}


@dataclass
class PaletteItem:
    kind: str
    title: str
    subtitle: str = ""
    glyph: str = ""
    qicon: QIcon | None = None
    emoji: str = ""
    badge: str = ""
    positions: tuple = ()
    score: float = 0.0
    run: Callable[[bool], None] | None = None
    complete: str = ""
    header: bool = False
    meta: dict = field(default_factory=dict)


class ResultModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[PaletteItem] = []

    def set_items(self, items: list[PaletteItem]) -> None:
        self.beginResetModel()
        self.items = items
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.items)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self.items[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return item
        if role == Qt.ItemDataRole.DisplayRole:
            return item.title
        return None

    def flags(self, index: QModelIndex):
        item = self.items[index.row()] if index.isValid() else None
        if item is None or item.header:
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable


class ResultDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index) -> QSize:
        item: PaletteItem = index.data(Qt.ItemDataRole.UserRole)
        return QSize(option.rect.width(), HEADER_H if item and item.header else ROW_H)

    def paint(self, p: QPainter, option, index) -> None:
        item: PaletteItem = index.data(Qt.ItemDataRole.UserRole)
        if item is None:
            return
        th = theme()
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(option.rect)
        if item.header:
            f = QFont(option.font)
            f.setPointSizeF(7.5)
            f.setWeight(QFont.Weight.Medium)
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
            p.setFont(f)
            p.setPen(th.c("text3"))
            p.drawText(r.adjusted(18, 4, -10, 0), Qt.AlignmentFlag.AlignVCenter, item.title.upper())
            p.restore()
            return
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            path = QPainterPath()
            path.addRoundedRect(r.adjusted(6, 2, -6, -2), 9, 9)
            p.fillPath(path, th.accent_alpha(0.20))
            p.fillRect(QRectF(r.left() + 6, r.top() + 12, 3, r.height() - 24), th.c("accent"))
        icon_r = QRectF(r.left() + 20, r.center().y() - 11, 22, 22)
        if item.qicon is not None and not item.qicon.isNull():
            pm = item.qicon.pixmap(QSize(18, 18), option.widget.devicePixelRatioF() if option.widget else 1.0)
            p.drawPixmap(QRect(int(icon_r.x()) + 2, int(icon_r.y()) + 2, 18, 18), pm)
        elif item.emoji:
            draw_emoji(p, icon_r, item.emoji, 15)
        else:
            draw_glyph(p, icon_r, item.glyph or "globe", th.c("accent") if selected else th.c("text2"), 15)
        x = icon_r.right() + 14
        right = r.right() - 16
        if item.badge:
            f = QFont(option.font)
            f.setPointSizeF(8)
            p.setFont(f)
            fm = p.fontMetrics()
            bw = fm.horizontalAdvance(item.badge) + 14
            br = QRectF(right - bw, r.center().y() - 10, bw, 20)
            path = QPainterPath()
            path.addRoundedRect(br, 6, 6)
            p.fillPath(path, th.c("input"))
            p.setPen(QPen(th.c("input_border"), 1))
            p.drawPath(path)
            p.setPen(th.c("text2"))
            p.drawText(br, Qt.AlignmentFlag.AlignCenter, item.badge)
            right = br.left() - 10
        title_font = QFont(option.font)
        title_font.setPointSizeF(10)
        bold = QFont(title_font)
        bold.setWeight(QFont.Weight.DemiBold)
        has_sub = bool(item.subtitle)
        sf = QFont(option.font)
        sf.setPointSizeF(8.5)
        tfm = QFontMetrics(title_font)
        sfm = QFontMetrics(sf)
        if has_sub:
            block = tfm.height() + 2 + sfm.height()
            top = r.center().y() - block / 2
            title_base = top + tfm.ascent()
            sub_base = top + tfm.height() + 2 + sfm.ascent()
        else:
            title_base = r.center().y() + (tfm.ascent() - tfm.descent()) / 2
            sub_base = 0.0
        self._draw_highlighted(p, x, right, title_base, item.title, set(item.positions), title_font, bold,
                               th.c("text"), th.c("accent"))
        if has_sub:
            p.setFont(sf)
            p.setPen(th.c("text3"))
            p.drawText(int(x), int(sub_base), sfm.elidedText(item.subtitle, Qt.TextElideMode.ElideMiddle,
                                                              int(right - x)))
        p.restore()

    @staticmethod
    def _draw_highlighted(p: QPainter, left: float, limit: float, baseline: float, text: str, positions: set,
                          normal: QFont, bold: QFont, color, accent) -> None:
        p.setFont(normal)
        fm_n = p.fontMetrics()
        if not positions:
            p.setPen(color)
            p.drawText(int(left), int(baseline), fm_n.elidedText(text, Qt.TextElideMode.ElideRight, int(limit - left)))
            return
        x = left
        for i, ch in enumerate(text):
            hit = i in positions
            p.setFont(bold if hit else normal)
            fm = p.fontMetrics()
            w = fm.horizontalAdvance(ch)
            if x + w > limit - fm.horizontalAdvance("…"):
                p.setFont(normal)
                p.setPen(color)
                p.drawText(int(x), int(baseline), "…")
                break
            p.setPen(accent if hit else color)
            p.drawText(int(x), int(baseline), ch)
            x += w


class ResultList(QListView):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("QListView{background:transparent;border:none;}"
                           "QListView::item{background:transparent;border:none;padding:0;}")
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.setItemDelegate(ResultDelegate(self))


class _ModeGlyph(QWidget):
    """Search / edit icon at the start of the input (no text until the user types)."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFixedSize(26, 26)
        self._glyph = "search"

    def set_mode(self, mode: str) -> None:
        self._glyph = {"edit": "edit", "current": "refresh"}.get(mode, "search")
        self.setToolTip({"edit": "Edit this card's address", "current": "Opens in this card"}.get(
            mode, "Opens in a new card"))
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        draw_glyph(p, QRectF(self.rect()), self._glyph, theme().c("text2"), 16)
        p.end()


class LazyToolbar(Overlay):
    def __init__(self, ctx: "AppContext", ui: "BrowserController", host: QWidget):
        super().__init__(host)
        self.ctx = ctx
        self.ui = ui
        self.mode = "new"
        self._insert_at: int | None = None
        self._suggestions: tuple[str, list[str]] = ("", [])
        self.panel = QFrame(self)
        self.panel.setObjectName("LazyPanel")
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(10, 8, 10, 8)
        pl.setSpacing(6)
        row = QHBoxLayout()
        row.setContentsMargins(10, 0, 4, 0)
        row.setSpacing(10)
        self.mode_chip = _ModeGlyph(self.panel)
        row.addWidget(self.mode_chip)
        self.edit = QLineEdit(self.panel)
        self.edit.setObjectName("LazyInput")
        f = self.edit.font()
        f.setPointSizeF(14)
        self.edit.setFont(f)
        self.edit.setFrame(False)
        row.addWidget(self.edit, 1)
        pl.addLayout(row)
        self.sep = QFrame(self.panel)
        self.sep.setFixedHeight(1)
        pl.addWidget(self.sep)
        self.model = ResultModel(self)
        self.list = ResultList(self.panel)
        self.list.setModel(self.model)
        pl.addWidget(self.list, 1)
        self.footer = QLabel(self.panel)
        self.footer.setProperty("muted", True)
        ff = self.footer.font()
        ff.setPointSizeF(8)
        self.footer.setFont(ff)
        pl.addWidget(self.footer)
        self.edit.textEdited.connect(self._on_text)
        self.edit.installEventFilter(self)
        self.list.clicked.connect(lambda idx: self._execute(idx, False))
        ctx.suggest.suggestions.connect(self._on_suggestions)
        theme().changed.connect(self._restyle)
        self._restyle()

    # ------------------------------------------------------------- styling
    def _restyle(self) -> None:
        t = theme().tokens
        self.panel.setStyleSheet(
            f"#LazyPanel{{background:{t['panel']};border:1px solid {t['panel_border']};border-radius:16px;}}"
            f"#LazyInput{{background:transparent;border:none;color:{t['text']};padding:8px 2px;}}")
        self.sep.setStyleSheet(f"background:{t['divider']};")

    def panel_rect(self) -> QRect:
        return self.panel.geometry()

    def _layout_panel(self) -> None:
        host = self.rect()
        w = min(740, max(420, host.width() - 120))
        rows = 0.0
        for it in self.model.items[:MAX_VISIBLE + 3]:
            rows += HEADER_H if it.header else ROW_H
        list_h = int(min(rows, MAX_VISIBLE * ROW_H)) if self.model.items else 0
        typing = bool(self.edit.text().strip())
        self.list.setVisible(list_h > 0)
        self.sep.setVisible(list_h > 0)
        self.footer.setVisible(typing)
        h = 8 + 46 + (7 + list_h if list_h else 0) + (6 + self.footer.sizeHint().height() if typing else 0) + 8
        top = max(24, int(host.height() * 0.13))
        self.panel.setGeometry((host.width() - w) // 2, top, w, min(h, host.height() - top - 24))
        self.update()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._layout_panel()

    # --------------------------------------------------------------- open
    def open(self, mode: str = "new", text: str = "", insert_at: int | None = None) -> None:
        self.mode = mode
        self._insert_at = insert_at
        tab = self.ctx.state.active_tab
        if mode in ("current", "edit") and tab is None:
            self.mode = mode = "new"
        self.mode_chip.set_mode(mode)
        if mode == "edit" and not text and tab is not None:
            text = tab.url
        self.edit.setText(text)
        other = "this card" if mode == "new" else "a new card"
        self.footer.setText(f"↑↓ to move, Enter to open, Shift+Enter to open in {other}, Tab to complete.   "
                            f"Prefixes: > commands, @ cards, * bookmarks, # history, $ passwords")
        self._suggestions = ("", [])
        self.refresh()
        self.open_overlay()
        self._layout_panel()
        self._focus_input()
        QTimer.singleShot(0, self._focus_input)
        QTimer.singleShot(200, self._focus_input)   # after the fade-in, when the caret can paint

    def _focus_input(self) -> None:
        if not self.isVisible():
            return
        win = self.window()
        if not win.isActiveWindow():
            win.activateWindow()
        self.edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        if self.edit.text() and not self.edit.hasSelectedText() and self.mode == "edit":
            self.edit.selectAll()

    def close_overlay(self) -> None:
        self.ctx.suggest.cancel()
        super().close_overlay()

    # ------------------------------------------------------------- input
    def eventFilter(self, obj, ev) -> bool:
        if obj is self.edit and ev.type() == QEvent.Type.KeyPress:
            key = ev.key()
            if key == Qt.Key.Key_Escape:
                self.close_overlay()
                return True
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
                step = {Qt.Key.Key_Down: 1, Qt.Key.Key_Up: -1, Qt.Key.Key_PageDown: 6, Qt.Key.Key_PageUp: -6}[key]
                self._move(step)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                alt = bool(ev.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier))
                self._execute(self.list.currentIndex(), alt)
                return True
            if key == Qt.Key.Key_Tab:
                item = self._current_item()
                if item and item.complete:
                    self.edit.setText(item.complete)
                    self._on_text(item.complete)
                return True
        return super().eventFilter(obj, ev)

    def _current_item(self) -> PaletteItem | None:
        idx = self.list.currentIndex()
        return idx.data(Qt.ItemDataRole.UserRole) if idx.isValid() else None

    def _move(self, step: int) -> None:
        items = self.model.items
        if not items:
            return
        row = self.list.currentIndex().row()
        direction = 1 if step > 0 else -1
        remaining = abs(step)
        r = row
        while remaining > 0:
            nxt = r + direction
            while 0 <= nxt < len(items) and items[nxt].header:
                nxt += direction
            if not 0 <= nxt < len(items):
                break
            r = nxt
            remaining -= 1
        if r != row and r >= 0:
            self.list.setCurrentIndex(self.model.index(r))
            self.list.scrollTo(self.model.index(r))

    def _on_text(self, _text: str) -> None:
        self.refresh()

    def _on_suggestions(self, query: str, items: list) -> None:
        if not self.isVisible():
            return
        if query == self._query_for_suggest():
            self._suggestions = (query, items)
            self.refresh(request=False)

    def _query_for_suggest(self) -> str:
        q = self.edit.text().strip()
        return "" if q[:1] in PREFIXES else q

    # ------------------------------------------------------------ execute
    def _target(self, alt: bool) -> str:
        base = "new" if self.mode == "new" else "current"
        if alt:
            return "current" if base == "new" else "new"
        return base

    def _open(self, url: QUrl, alt: bool) -> None:
        self.close_overlay()
        target = self._target(alt)
        self.ui.open_url(url, target, index=self._insert_at if target == "new" else None)

    def _execute(self, index: QModelIndex, alt: bool) -> None:
        item: PaletteItem | None = index.data(Qt.ItemDataRole.UserRole) if index.isValid() else None
        if item is None:
            text = self.edit.text().strip()
            if not text:
                return
            item = self._primary_items(text)[0]
        if item.run is not None:
            item.run(alt)

    # ------------------------------------------------------------ results
    def _incognito(self) -> bool:
        sp = self.ctx.state.active_space
        return bool(sp and sp.incognito)

    def _primary_items(self, q: str) -> list[PaletteItem]:
        ctx = self.ctx
        remember = not self._incognito()
        items: list[PaletteItem] = []
        kw = ctx.search.parse_keyword(q)
        if kw:
            eng, query = kw
            items.append(PaletteItem("engine", f"Search {eng.name} for “{query}”", eng.build(query), glyph="search",
                                     badge=eng.keyword,
                                     run=lambda alt, t=q: self._open(ctx.resolve_input(t, remember), alt)))
        is_url = looks_like_url(q, ctx.privacy.dev_hosts())
        search_item = PaletteItem(
            "search", f"Search {ctx.search.default_name} for “{q}”", "", glyph="search", badge="Search",
            run=lambda alt, t=q: (ctx.search.remember(t) if remember else None,
                                  self._open(ctx.search.search_url(t), alt)))
        if is_url:
            url = to_url(q)
            if url.isLocalFile():
                path = os.path.normpath(url.toLocalFile())
                # Never touch the disk while typing: a network path can take seconds to answer.
                folder = q.rstrip("\"' ").endswith(("\\", "/")) or not os.path.splitext(path)[1]
                items.append(PaletteItem("go", f"Open {path}", "Folder on this PC" if folder else "File on this PC",
                                         glyph="folder" if folder else "open_file", badge="Open", complete=path,
                                         run=lambda alt, u=url: self._open(u, alt)))
                items.append(search_item)
                return items
            target = ctx.privacy.dev_target(url.host())
            sub = url.toString()
            if target:
                sub += f"  (routed to {target[0]}:{target[1]})"
            items.append(PaletteItem("go", f"Open {pretty_url(url)}", sub, glyph="globe", badge="Go",
                                     complete=url.toString(), run=lambda alt, u=url: self._open(u, alt)))
            items.append(search_item)
        else:
            items.insert(0 if not kw else 1, search_item)
        return items

    def _section(self, out: list, title: str, items: list[PaletteItem]) -> None:
        if items:
            out.append(PaletteItem("header", title, header=True))
            out.extend(items)

    def refresh(self, request: bool = True) -> None:
        raw = self.edit.text()
        q = raw.strip()
        scope = None
        if q[:1] in PREFIXES:
            scope = PREFIXES[q[0]]
            q = q[1:].strip()
        ctx = self.ctx
        out: list[PaletteItem] = []
        if request:
            sq = self._query_for_suggest()
            if sq and ctx.settings.get("search.suggestions") and not self._incognito() \
                    and not looks_like_url(sq, ctx.privacy.dev_hosts()):
                ctx.suggest.request(sq)
            else:
                ctx.suggest.cancel()
        if not q and scope is None:
            pass  # nothing is shown until the user starts typing
        else:
            if scope is None:
                self._section(out, "Top result", self._primary_items(q))
            if scope in (None, "card"):
                self._section(out, "Open cards", self._cards(q, 12 if scope else 4))
            if scope in (None, "bookmark"):
                self._section(out, "Bookmarks", self._bookmarks(q, 20 if scope else 3))
            if scope in (None, "history"):
                self._section(out, "History", self._history(q, 25 if scope else 5, out))
            if scope is None:
                self._section(out, "Suggestions", self._suggest_items(q))
            if scope in (None, "command"):
                self._section(out, "Commands", self._commands(q, 40 if scope else 4))
            if scope == "password" or (scope is None and len(q) >= 3):
                self._section(out, "Passwords", self._passwords(q, 12 if scope else 3))
        self.model.set_items(out)
        for i, it in enumerate(out):
            if not it.header:
                self.list.setCurrentIndex(self.model.index(i))
                break
        self._layout_panel()

    def _card_item(self, t, positions) -> PaletteItem:
        sp = self.ctx.state.space_of(t)
        active_space = self.ctx.state.active_space
        other_space = sp is not None and active_space is not None and sp.id != active_space.id
        subtitle = pretty_url(t.url)
        if other_space:
            subtitle = f"{sp.name} · {subtitle}"
        if t.sleeping:
            subtitle = "💤 " + subtitle
        return PaletteItem("card", t.display_title(), subtitle, qicon=t.icon if not t.icon.isNull() else None,
                           glyph="page", positions=positions, badge="Switch",
                           emoji=sp.icon if other_space and t.icon.isNull() else "",
                           run=lambda alt, tid=t.id: (self.close_overlay(),
                                                      self.ui.activate_card(tid, Qt.KeyboardModifier.NoModifier,
                                                                            wake=True, center=True)))

    def _cards(self, q: str, limit: int) -> list[PaletteItem]:
        scored = []
        for t in self.ctx.state.all_tabs():
            m = best_match(q, t.display_title(), t.url) if q else None
            if q and m is None:
                continue
            score = (m.score if m else 0) + (5 if t.space_id == self.ctx.state.active_space_id else 0)
            scored.append((score, t, m.positions if m else ()))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._card_item(t, pos) for _s, t, pos in scored[:limit]]

    def _bookmarks(self, q: str, limit: int) -> list[PaletteItem]:
        scored = []
        for b in self.ctx.bookmarks.all():
            m = best_match(q, b.title, b.url, b.folder) if q else None
            if q and m is None:
                continue
            scored.append((m.score if m else 0, b, m.positions if m else ()))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [PaletteItem("bookmark", b.title or b.url, pretty_url(b.url), qicon=self.ctx.favicons.get(b.url),
                            glyph="star", positions=pos, complete=b.url,
                            run=lambda alt, u=b.url: self._open(QUrl(u), alt)) for _s, b, pos in scored[:limit]]

    def _history(self, q: str, limit: int, existing: list) -> list[PaletteItem]:
        if self._incognito() and not q:
            return []
        shown = {it.complete for it in existing if it.complete}
        shown |= {t.url for t in self.ctx.state.all_tabs()}
        scored = []
        for page in self.ctx.history.pages_matching(q.split()[0] if q else "", 150):
            if page.url in shown:
                continue
            m = best_match(q, page.title, page.url) if q else None
            if q and m is None:
                continue
            scored.append(((m.score if m else 0) + page.frecency() * 0.8, page, m.positions if m else ()))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [PaletteItem("history", p.title or pretty_url(p.url), pretty_url(p.url), qicon=self.ctx.favicons.get(p.url),
                            glyph="history", positions=pos, complete=p.url,
                            run=lambda alt, u=p.url: self._open(QUrl(u), alt)) for _s, p, pos in scored[:limit]]

    def _suggest_items(self, q: str) -> list[PaletteItem]:
        sq, items = self._suggestions
        if sq != q or not items:
            return []
        remember = not self._incognito()
        out = []
        for s in items:
            if s.strip().lower() == q.lower():
                continue
            m = fuzzy_match(q, s)
            out.append(PaletteItem("suggest", s, "", glyph="search", positions=m.positions if m else (), complete=s,
                                   run=lambda alt, t=s: (self.ctx.search.remember(t) if remember else None,
                                                         self._open(self.ctx.search.search_url(t), alt))))
        return out[:5]

    def _commands(self, q: str, limit: int) -> list[PaletteItem]:
        scored = []
        for cmd in self.ctx.commands.all():
            if not cmd.palette or (cmd.enabled and not cmd.enabled()):
                continue
            m = best_match(q, cmd.title, cmd.keywords, cmd.category) if q else None
            if q and m is None:
                continue
            scored.append((m.score if m else 0, cmd, m.positions if m else ()))
        if not q:
            scored.sort(key=lambda x: (x[1].category, x[1].title))
        else:
            scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for _s, cmd, pos in scored[:limit]:
            state = cmd.state() if cmd.state else None
            title = cmd.title + (f": {state}" if state else "")
            out.append(PaletteItem("command", title, cmd.category, glyph=cmd.icon or "lightning",
                                   badge=cmd.shortcut_text(), positions=pos,
                                   run=lambda alt, c=cmd.id: (self.close_overlay(), self.ctx.commands.run(c))))
        return out

    def _passwords(self, q: str, limit: int) -> list[PaletteItem]:
        vault = self.ctx.vault
        if vault.mode == "master" and vault.is_locked:
            if not q:
                return [PaletteItem("password", "Unlock the password vault", "Master password required",
                                    glyph="lock", run=lambda alt: (self.close_overlay(), self.ui.unlock_vault()))]
            return []
        scored = []
        space_id = self.ctx.state.active_space_id
        for cred in vault.entries():
            if cred.space_id and cred.space_id != space_id:
                continue
            m = best_match(q, cred.host, cred.username) if q else None
            if q and m is None:
                continue
            scored.append((m.score if m else 0, cred))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        tab = self.ctx.state.active_tab
        for _s, cred in scored[:limit]:
            can_fill = tab is not None and strip_www(QUrl(tab.url).host()) == cred.host
            out.append(PaletteItem(
                "password", cred.host, f"{cred.username or '(no username)'} · "
                                       f"{'Enter fills this card' if can_fill else 'Enter copies password'}"
                                       " · Shift+Enter copies username",
                glyph="key", badge="Fill" if can_fill else "Copy",
                run=lambda alt, c=cred, f=can_fill: self._use_password(c, f, alt)))
        return out

    def _use_password(self, cred, can_fill: bool, alt: bool) -> None:
        self.close_overlay()
        if alt:
            QGuiApplication.clipboard().setText(cred.username)
            self.ui.toast("Username copied", "copy")
            return
        if can_fill:
            self.ui.fill_password(cred)
        else:
            self.ui.copy_secret(cred.password, "Password copied. The clipboard clears in 30 seconds")
