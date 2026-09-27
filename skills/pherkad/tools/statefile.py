#!/usr/bin/env python3
"""statefile: write the tools' state files so they cannot be cut or lost.

Every file a tool keeps and later reads back (the correction ledger, the
samples manifest, the decision store, a promoted overlay, a fingerprint) is
written through here. Two failures it rules out:

- A cut file. Writing in place truncates first, so an interrupted write leaves
  a file that is empty or half a JSON document; the next load either fails or,
  worse, reads fewer records and the next save drops the rest. ``write_text``
  writes a temporary file beside the target, flushes and fsyncs it, and swaps
  it in with ``os.replace``, which is atomic: a reader sees the old file or the
  new one, never a part.
- A lost update. Two runs that each load, change, and save the same file keep
  only the second one's changes. ``locked`` takes an exclusive lock on a
  sidecar ``<file>.lock`` for the whole load-change-save, so the second run
  loads after the first has saved. Where ``fcntl`` is missing (Windows) it
  degrades to no lock; the write itself stays atomic.

Stdlib only.
"""
from __future__ import annotations
import contextlib
import json
import os
import tempfile

try:
    import fcntl
except ImportError:  # Windows: atomic writes still hold, locking does not
    fcntl = None


def write_text(path: str, text: str) -> None:
    """Replace ``path`` with ``text`` atomically, keeping an existing file's mode.
    A symlink is followed and its target replaced, never the link itself: the
    voice files in the pherkad root are links into another repository."""
    path = os.path.realpath(path)
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if os.path.exists(path):
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        else:
            os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def write_json(path: str, obj, *, indent=2, ensure_ascii=False, sort_keys=False, newline=True) -> None:
    """Atomically write ``obj`` as JSON."""
    text = json.dumps(obj, indent=indent, ensure_ascii=ensure_ascii, sort_keys=sort_keys)
    write_text(path, text + ("\n" if newline else ""))


@contextlib.contextmanager
def locked(path: str):
    """Hold an exclusive lock for one load-change-save of ``path``."""
    if fcntl is None:
        yield
        return
    lock_path = os.path.realpath(path) + ".lock"
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, "a") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
