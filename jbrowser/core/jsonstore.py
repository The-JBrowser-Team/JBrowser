"""Crash-safe JSON / binary persistence helpers."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write via temp file + os.replace so a crash never leaves a torn file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
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
