"""Carpetas temporales de trabajo: cada proceso usa una carpeta propia que se borra sola."""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

WORK = Path(os.environ.get("BSOBPDF_TMP") or (Path(tempfile.gettempdir()) / "bsobpdf"))
MAX_AGE = int(os.environ.get("BSOBPDF_MAX_AGE", 3 * 3600))  # segundos
_last_clean = 0.0
_lock = threading.Lock()


def new_job() -> tuple[str, Path]:
    jid = uuid.uuid4().hex
    d = WORK / jid
    (d / "in").mkdir(parents=True, exist_ok=True)
    (d / "out").mkdir(parents=True, exist_ok=True)
    return jid, d


def job_dir(jid: str) -> Path | None:
    if not jid or not all(c in "0123456789abcdef" for c in jid) or len(jid) != 32:
        return None
    d = WORK / jid
    return d if d.is_dir() else None


def cleanup(force: bool = False) -> None:
    global _last_clean
    now = time.time()
    if not force and now - _last_clean < 600:
        return
    with _lock:
        _last_clean = now
        if not WORK.exists():
            return
        for d in WORK.iterdir():
            try:
                if d.is_dir() and now - d.stat().st_mtime > MAX_AGE:
                    shutil.rmtree(d, ignore_errors=True)
            except OSError:
                pass
