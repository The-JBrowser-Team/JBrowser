"""Single-instance guard: a second launch forwards its URLs to the running window.

Two processes must never share the same Chromium profile directories, and opening a link
from another app should land in the existing window as a new card.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    received = pyqtSignal(str)

    def __init__(self, key: str, parent: QObject | None = None):
        super().__init__(parent)
        self.key = key
        self.server: QLocalServer | None = None

    def notify_existing(self, payload: str) -> bool:
        sock = QLocalSocket()
        sock.connectToServer(self.key)
        if not sock.waitForConnected(500):
            return False
        sock.write(payload.encode("utf-8"))
        sock.flush()
        sock.waitForBytesWritten(1500)
        sock.disconnectFromServer()
        return True

    def listen(self) -> None:
        QLocalServer.removeServer(self.key)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.listen(self.key)
        self.server.newConnection.connect(self._on_connection)

    def close(self) -> None:
        """Stop answering so a restarted instance can take over the name."""
        if self.server is not None:
            self.server.close()
            self.server = None

    def _on_connection(self) -> None:
        while self.server and self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            buf = bytearray()

            def read(s=sock, b=buf):
                b.extend(bytes(s.readAll()))

            def done(s=sock, b=buf):
                read()
                if b:
                    self.received.emit(b.decode("utf-8", "replace"))
                s.deleteLater()

            sock.readyRead.connect(read)
            sock.disconnected.connect(done)
