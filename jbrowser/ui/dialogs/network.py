"""Proxy configuration (global or per space) and the localhost developer toolkit."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtNetwork import QTcpSocket
from PyQt6.QtWidgets import (QButtonGroup, QComboBox, QDialogButtonBox, QFormLayout, QGridLayout, QHBoxLayout,
                             QHeaderView, QLabel, QLineEdit, QPushButton, QRadioButton, QSpinBox, QTableWidget,
                             QTableWidgetItem, QWidget)

from jbrowser.models.space import Space
from jbrowser.services.network import DEV_PORTS, PortProbe, normalize_proxy, protect_secret, reveal_secret
from jbrowser.ui.chrome_window import ChromeWindow
from jbrowser.ui.dialogs.base import JDialog, heading


class ProxyDialog(JDialog):
    def __init__(self, ctx, space: Space | None, parent: QWidget | None = None):
        title = f"Proxy for {space.name}" if space else "Proxy settings"
        super().__init__(title, parent, (560, 520), modal=True)
        self.ctx = ctx
        self.space = space
        cfg = normalize_proxy(space.proxy if space else ctx.settings.get("network.proxy"))
        if space is not None and not space.proxy:
            cfg["mode"] = "inherit"
        self.root.addWidget(heading(title))
        if space is not None:
            note = ("Chromium runs one network stack per process, so a space override routes all traffic while this "
                    "space is in the foreground; it is re-applied instantly whenever you switch spaces.")
        else:
            note = "Applies to every space without its own override. HTTP and SOCKS5 changes apply instantly."
        n = QLabel(note)
        n.setWordWrap(True)
        n.setProperty("muted", True)
        self.root.addWidget(n)
        self.group = QButtonGroup(self)
        modes = ([("inherit", "Use global setting")] if space else []) + [
            ("direct", "No proxy (direct connection)"), ("system", "Use Windows proxy settings"),
            ("manual", "Manual proxy configuration")]
        for value, label in modes:
            rb = QRadioButton(label)
            rb.setProperty("mode", value)
            rb.setChecked(cfg["mode"] == value)
            self.group.addButton(rb)
            self.root.addWidget(rb)
        form = QFormLayout()
        self.type = QComboBox()
        self.type.addItem("HTTP (CONNECT tunnel for HTTPS)", "http")
        self.type.addItem("SOCKS5", "socks5")
        if space is None:
            self.type.addItem("HTTPS (TLS to the proxy, applies after a restart)", "https")
        idx = self.type.findData(cfg["type"])
        self.type.setCurrentIndex(max(0, idx))
        self.host = QLineEdit(cfg["host"])
        self.host.setPlaceholderText("proxy.example.com")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(cfg["port"] or 8080))
        self.user = QLineEdit(cfg["username"])
        self.password = QLineEdit(reveal_secret(cfg["password"]))
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Type", self.type)
        form.addRow("Host", self.host)
        form.addRow("Port", self.port)
        form.addRow("Username", self.user)
        form.addRow("Password", self.password)
        self.form_box = QWidget()
        self.form_box.setLayout(form)
        self.root.addWidget(self.form_box)
        test_row = QHBoxLayout()
        self.test_btn = QPushButton("Test connection to proxy")
        self.test_btn.clicked.connect(self._test)
        self.test_result = QLabel()
        self.test_result.setProperty("muted", True)
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.test_result, 1)
        self.root.addLayout(test_row)
        self.root.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Save).setProperty("primary", True)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        self.root.addWidget(bb)
        self.group.buttonToggled.connect(lambda *_: self._sync())
        self._sync()

    def _mode(self) -> str:
        b = self.group.checkedButton()
        return b.property("mode") if b else "direct"

    def _sync(self) -> None:
        manual = self._mode() == "manual"
        self.form_box.setEnabled(manual)
        self.test_btn.setEnabled(manual)

    def _test(self) -> None:
        host, port = self.host.text().strip(), self.port.value()
        if not host:
            return
        self.test_result.setText("Connecting…")
        sock = QTcpSocket(self)
        sock.connected.connect(lambda: (self.test_result.setText(f"✓ {host}:{port} is reachable"), sock.abort()))
        sock.errorOccurred.connect(lambda _e: self.test_result.setText(f"✗ {sock.errorString()}"))
        sock.connectToHost(host, port)

    def _save(self) -> None:
        mode = self._mode()
        if self.space is not None and mode == "inherit":
            self.ctx.state.update_space(self.space.id, proxy=None)
            self.accept()
            return
        cfg = {"mode": mode, "type": self.type.currentData(), "host": self.host.text().strip(),
               "port": self.port.value(), "username": self.user.text().strip(),
               "password": protect_secret(self.password.text())}
        if mode == "manual" and not cfg["host"]:
            self.host.setFocus()
            return
        if self.space is not None:
            self.ctx.state.update_space(self.space.id, proxy=cfg)
        else:
            previous = normalize_proxy(self.ctx.settings.get("network.proxy"))
            self.ctx.settings.set("network.proxy", cfg)
            if (cfg["type"] == "https") != (previous["type"] == "https" and previous["mode"] == "manual") \
                    and mode == "manual":
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(self, "Restart required",
                                        "HTTPS (TLS) proxies are configured at startup. Restart JBrowser to apply.")
        self.accept()


class DevHostsDialog(ChromeWindow):
    def __init__(self, ctx, ui, parent: QWidget | None = None):
        super().__init__("Localhost developer toolkit", parent, (720, 600))
        self.ctx = ctx
        self.ui = ui
        self.root.addWidget(heading("Localhost developer toolkit"))
        lab = QLabel("Map friendly host names to local ports. Requests to a mapped host (typed in the Lazy Toolbar, "
                     "linked, or fetched by a page) are routed to the target, for example app.test → 127.0.0.1:3000.")
        lab.setWordWrap(True)
        lab.setProperty("muted", True)
        self.root.addWidget(lab)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Host name", "Target (host:port)", "Enabled"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        for m in ctx.settings.get("network.dev_hosts") or []:
            self._add_row(m.get("host", ""), m.get("target", ""), m.get("enabled", True))
        self.root.addWidget(self.table, 1)
        row = QHBoxLayout()
        add = QPushButton("Add mapping")
        add.clicked.connect(lambda: self._add_row("myapp.test", "127.0.0.1:3000", True))
        rm = QPushButton("Remove selected")
        rm.clicked.connect(lambda: [self.table.removeRow(r) for r in sorted({i.row() for i in
                                                                            self.table.selectedIndexes()},
                                                                           reverse=True)])
        save = QPushButton("Save mappings")
        save.setProperty("primary", True)
        save.clicked.connect(self._save)
        row.addWidget(add)
        row.addWidget(rm)
        row.addStretch(1)
        row.addWidget(save)
        self.root.addLayout(row)

        self.root.addWidget(heading("Quick launch", sub=True))
        grid = QGridLayout()
        self.status: dict[int, QLabel] = {}
        self.probe = PortProbe(self)
        self.probe.result.connect(self._on_probe)
        for i, (port, desc) in enumerate(DEV_PORTS):
            dot = QLabel("●")
            dot.setToolTip("Checking…")
            self.status[port] = dot
            btn = QPushButton(f"localhost:{port}")
            btn.setToolTip(desc)
            btn.clicked.connect(lambda _c=False, p=port: self.ui.open_localhost(p))
            d = QLabel(desc)
            d.setProperty("muted", True)
            grid.addWidget(dot, i // 2, (i % 2) * 3)
            grid.addWidget(btn, i // 2, (i % 2) * 3 + 1)
            grid.addWidget(d, i // 2, (i % 2) * 3 + 2)
            self.probe.probe(port)
        self.root.addLayout(grid)
        custom = QHBoxLayout()
        self.custom_port = QSpinBox()
        self.custom_port.setRange(1, 65535)
        self.custom_port.setValue(4000)
        go = QPushButton("Open port")
        go.clicked.connect(lambda: self.ui.open_localhost(self.custom_port.value()))
        refresh = QPushButton("Re-check ports")
        refresh.clicked.connect(lambda: [self.probe.probe(p) for p, _ in DEV_PORTS])
        custom.addWidget(QLabel("Custom port"))
        custom.addWidget(self.custom_port)
        custom.addWidget(go)
        custom.addStretch(1)
        custom.addWidget(refresh)
        self.root.addLayout(custom)

    def _add_row(self, host: str, target: str, enabled: bool) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(host))
        self.table.setItem(r, 1, QTableWidgetItem(target))
        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        chk.setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
        self.table.setItem(r, 2, chk)

    def _save(self) -> None:
        out = []
        for r in range(self.table.rowCount()):
            host = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip().lower()
            target = (self.table.item(r, 1).text() if self.table.item(r, 1) else "").strip()
            if not host or not target:
                continue
            if "://" in host:
                host = QUrl(host).host()
            if ":" not in target:
                target = f"127.0.0.1:{target}" if target.isdigit() else f"{target}:80"
            out.append({"host": host, "target": target,
                        "enabled": self.table.item(r, 2).checkState() == Qt.CheckState.Checked})
        self.ctx.settings.set("network.dev_hosts", out)
        self.ui.toast(f"Saved {len(out)} developer host mapping(s)", "developer")

    def _on_probe(self, port: int, ok: bool) -> None:
        dot = self.status.get(port)
        if dot is not None:
            dot.setStyleSheet(f"color: {'#3ecf8e' if ok else '#8a8a93'};")
            dot.setToolTip("Something is listening" if ok else "Nothing listening")
