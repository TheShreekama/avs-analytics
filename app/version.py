"""Build stamp — which copy of the source is actually running.

The app is distributed by copying a folder, so "am I on the latest build?" is a
real question: a browser refresh re-runs the script inside the *same* Python
process, and a copy that landed in the wrong directory looks identical from the
UI.  The stamp answers it from the files themselves rather than a number someone
has to remember to bump:

  * **build time** — the newest modification time across the Python sources,
    to the minute (``2026-08-26 17:42``);
  * **fingerprint** — six characters of a hash over those files' contents, so two
    machines running identical code show the same value even if the copy dates
    differ.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from .config import APP_VERSION, ROOT_DIR

_SOURCE_GLOBS = ("Home.py", "app/**/*.py")


def _source_files() -> list[Path]:
    files: list[Path] = []
    for pattern in _SOURCE_GLOBS:
        files.extend(p for p in ROOT_DIR.glob(pattern) if p.is_file())
    return sorted(files)


@lru_cache(maxsize=1)
def build_stamp() -> tuple[str, str]:
    """``(build time, fingerprint)`` for the running source tree."""
    files = _source_files()
    if not files:
        return "unknown", "------"
    newest = max(p.stat().st_mtime for p in files)
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode("utf-8"))
        try:
            digest.update(path.read_bytes())
        except OSError:                      # unreadable file: fingerprint the name only
            continue
    return (datetime.fromtimestamp(newest).strftime("%Y-%m-%d %H:%M"),
            digest.hexdigest()[:6])


def version_line() -> str:
    """One-line version for the sidebar / console: v1.0.0 · build … · fingerprint."""
    built, fingerprint = build_stamp()
    return f"v{APP_VERSION} · build {built} · {fingerprint}"
