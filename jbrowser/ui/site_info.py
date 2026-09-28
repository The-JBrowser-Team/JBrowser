"""Site information panel opened from the security icon in the address pill."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPoint, QRectF, QSize, Qt, QUrl
from PyQt6.QtGui import QGuiApplication, QPainter, QPainterPath, QPen
from PyQt6.QtWebEngineCore import QWebEnginePermission
from PyQt6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from jbrowser.core.urls import is_local_host, strip_www
from jbrowser.models.tab import Tab
from jbrowser.services.permissions import describe
from jbrowser.ui.icons import draw_glyph
from jbrowser.ui.theme import theme
from jbrowser.ui.titlebar import security_state, suspicious_idn
from jbrowser.ui.widgets import ToggleSwitch

if TYPE_CHECKING:
    from jbrowser.context import AppContext
    from jbrowser.ui.controller import BrowserController

STATES = [("Ask", "reset"), ("Allow", "grant"), ("Block", "deny")]


class _GlyphLabel(QWidget):
    def __init__(self, glyph: str, token: str, parent: QWidget):
        super().__init__(parent)
        self.glyph, self.token = glyph, token
        self.setFixedSize(22, 22)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        draw_glyph(p, QRectF(self.rect()), self.glyph, theme().c(self.token), 14)
        p.end()


class SiteInfoPopup(QFrame):
    def __init__(self, ctx: "AppContext", ui: "BrowserController", tab: Tab, parent: QWidget):
        super().__init__(parent, Qt.WindowType.Popup)
        self.ctx, self.ui, self.tab = ctx, ui, tab
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedWidth(380)
        url = QUrl(tab.url)
        host = strip_www(url.host()) or url.toDisplayString()
        space = ctx.state.space_of(tab)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        head = QHBoxLayout()
        icon = QLabel(self)
        if not tab.icon.isNull():
            icon.setPixmap(tab.icon.pixmap(QSize(20, 20)))
        head.addWidget(icon)
        title = QLabel(host, self)
        f = title.font()
        f.setPointSizeF(11.5)
        title.setFont(f)
        head.addWidget(title, 1)
        lay.addLayout(head)

        glyph, token, _label = security_state(ctx, tab)
        if tab.title == "Dangerous site blocked":
            text = "JBrowser blocked this site because it is listed as phishing or malware."
        elif url.scheme() == "https":
            text = "Connection is secure. Information you send is encrypted on its way to this site."
        elif url.scheme() == "http" and (is_local_host(url.host()) or ctx.privacy.dev_target(url.host())):
            text = "Local development server on this computer."
        elif url.scheme() == "http":
            text = ("Connection is not secure. Anything you type here, such as passwords or card numbers, "
                    "could be read by others on your network.")
        else:
            text = "This is a local or built-in page."
        lay.addLayout(self._row(glyph, token, text))
        if suspicious_idn(url):
            lay.addLayout(self._row("warning", "warning",
                                    "This address mixes letters from different alphabets, a trick used by fake sites. "
                                    f"Its real form is {url.host(QUrl.ComponentFormattingOption.FullyEncoded)}."))
        lay.addWidget(self._divider())

        # Privacy
        lay.addLayout(self._row("shield", "accent",
                                f"{tab.blocked} tracker{'s' if tab.blocked != 1 else ''} blocked on this page"))
        prot = QHBoxLayout()
        lab = QLabel("Tracker and fingerprint protection for this site", self)
        lab.setWordWrap(True)
        prot.addWidget(lab, 1)
        sw = ToggleSwitch(not ctx.privacy.is_allowlisted(host), self)
        sw.toggled.connect(lambda on, h=host: (ctx.privacy.set_site_protection(h, on),
                                               ui.toast("Reload the page to apply the change", "shield")))
        prot.addWidget(sw)
        lay.addLayout(prot)
        cookies = ctx.cookies.cookies_for_host(space.id, url.host()) if space else []
        ck = QHBoxLayout()
        ck.addWidget(_GlyphLabel("fingerprint", "text2", self))
        ck.addWidget(QLabel(f"{len(cookies)} cookie{'s' if len(cookies) != 1 else ''} stored in this space", self), 1)
        manage = QPushButton("Manage", self)
        manage.setFlat(True)
        manage.clicked.connect(lambda: (self.close(), ui.open_dialog("cookies")))
        ck.addWidget(manage)
        lay.addLayout(ck)

        # Permissions
        prof = ctx.profiles.get(space.id) if space else None
        perms = []
        if prof is not None and url.host():
            origin = QUrl(f"{url.scheme()}://{url.authority()}")
            perms = [p for p in prof.listPermissionsForOrigin(origin) if p.isValid()]
        if perms:
            lay.addWidget(self._divider())
            cap = QLabel("Permissions", self)
            cap.setProperty("muted", True)
            lay.addWidget(cap)
            for perm in perms:
                name, _phrase, g = describe(perm.permissionType())
                row = QHBoxLayout()
                row.addWidget(_GlyphLabel(g, "text2", self))
                row.addWidget(QLabel(name, self), 1)
                combo = QComboBox(self)
                for label, _m in STATES:
                    combo.addItem(label)
                combo.setCurrentIndex({QWebEnginePermission.State.Granted: 1,
                                       QWebEnginePermission.State.Denied: 2}.get(perm.state(), 0))
                combo.currentIndexChanged.connect(
                    lambda i, p=QWebEnginePermission(perm): getattr(p, STATES[i][1])())
                row.addWidget(combo)
                lay.addLayout(row)
        if abs(tab.zoom - 1.0) > 0.001:
            zr = QHBoxLayout()
            zr.addWidget(_GlyphLabel("zoom_in", "text2", self))
            zr.addWidget(QLabel(f"Zoom {round(tab.zoom * 100)}%", self), 1)
            reset = QPushButton("Reset", self)
            reset.setFlat(True)
            reset.clicked.connect(lambda: (ui.zoom(0), self.close()))
            zr.addWidget(reset)
            lay.addLayout(zr)

        lay.addWidget(self._divider())
        actions = QHBoxLayout()
        clear = QPushButton("Clear site data", self)
        clear.clicked.connect(lambda: (self.close(), ui.clear_site_data(tab.id)))
        forget = QPushButton("Forget this site", self)
        forget.setProperty("danger", True)
        forget.clicked.connect(lambda: (self.close(), ui.forget_site(host)))
        actions.addWidget(clear)
        actions.addWidget(forget)
        lay.addLayout(actions)
        copy = QPushButton("Copy link without trackers", self)
        copy.setFlat(True)
        copy.clicked.connect(lambda: (self.close(), ui.copy_clean_link(tab.id)))
        lay.addWidget(copy, 0, Qt.AlignmentFlag.AlignLeft)

    def _row(self, glyph: str, token: str, text: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(_GlyphLabel(glyph, token, self), 0, Qt.AlignmentFlag.AlignTop)
        lab = QLabel(text, self)
        lab.setWordWrap(True)
        row.addWidget(lab, 1)
        return row

    def _divider(self) -> QFrame:
        d = QFrame(self)
        d.setFixedHeight(1)
        d.setStyleSheet(f"background:{theme().tokens['divider']};")
        return d

    def popup_at(self, pos: QPoint) -> None:
        self.adjustSize()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        x = min(max(avail.left() + 8, pos.x()), avail.right() - self.width() - 8)
        y = min(pos.y(), avail.bottom() - self.height() - 8)
        self.move(x, y)
        self.show()

    def paintEvent(self, _e) -> None:
        th = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), th.c("dialog_solid"))
        path = QPainterPath()
        path.addRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
        p.setPen(QPen(th.c("panel_border"), 1))
        p.drawPath(path)
        p.end()
