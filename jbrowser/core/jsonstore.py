"""Crash-safe JSON / binary persistence helpers."""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Antivirus scanners and the search indexer briefly open files that were just written, and Windows
# refuses to replace a file while another program has it open ("Access is denied"). Retrying for up
# to ~2.5 seconds rides that out instead of losing the save.
_REPLACE_ATTEMPTS = 20


def _replace(src: str, dst: Path) -> None:
    delay = 0.02
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(src, dst)
            if attempt:
                log.info("Saved %s after %d retries (the file was briefly in use)", dst.name, attempt)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 1.5, 0.2)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write via temp file + os.replace so a crash never leaves a torn file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        _replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_bytes(path, json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8"))


def read_json(path: Path, default: Any) -> Any:
    try:
        with open(path, "rb") as fh:
            return json.loads(fh.read().decode("utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        log.warning("Could not read %s (%s); keeping a backup and using defaults", path, exc)
        try:
            os.replace(path, path.with_suffix(path.suffix + ".corrupt"))
        except OSError:
            pass
        return default
