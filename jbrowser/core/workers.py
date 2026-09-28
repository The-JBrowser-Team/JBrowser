"""Background download helpers shared by the tracker-list and threat-list updaters.

Qt aborts the whole process if a ``QThread`` object is destroyed while its thread is still
running, so downloads are cancellable (streamed in chunks, short timeouts) and
:func:`stop_worker` makes sure a worker can never be destroyed mid-flight during shutdown.
"""
from __future__ import annotations

import logging
from typing import Callable

from PyQt6.QtCore import QThread

log = logging.getLogger(__name__)

MAX_LIST_BYTES = 64 * 1024 * 1024
_abandoned: list[QThread] = []   # workers still running at shutdown; kept alive until the process exits


def fetch_text(url: str, headers: dict, proxies: dict | None, cancelled: Callable[[], bool]) -> str:
    """Download ``url`` as text, giving up quickly when ``cancelled()`` turns true."""
    import requests

    with requests.get(url, timeout=(10, 20), headers=headers, proxies=proxies or None, stream=True) as r:
        r.raise_for_status()
        chunks: list[bytes] = []
        size = 0
        for chunk in r.iter_content(64 * 1024):
            if cancelled():
                raise InterruptedError("cancelled")
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_LIST_BYTES:
                raise ValueError("list is unexpectedly large")
        return b"".join(chunks).decode(r.encoding or "utf-8", "replace")


def stop_worker(worker: QThread | None, timeout_ms: int = 2000) -> None:
    """Cancel ``worker`` and wait briefly; if it is still busy, detach it so it is never destroyed."""
    if worker is None:
        return
    try:
        if not worker.isRunning():
            return
        worker.requestInterruption()
        try:
            worker.done.disconnect()
        except (TypeError, AttributeError):
            pass
        if worker.wait(timeout_ms):
            return
        from PyQt6 import sip

        log.info("Background download still running at shutdown; detaching it")
        worker.setParent(None)
        sip.transferto(worker, None)
        _abandoned.append(worker)
    except RuntimeError:
        pass
