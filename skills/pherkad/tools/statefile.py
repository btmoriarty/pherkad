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
import sys
import tempfile
import time

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


LOCK_TIMEOUT = float(os.environ.get("PHERKAD_LOCK_TIMEOUT", "10"))


@contextlib.contextmanager
def locked(path: str, timeout: float | None = None):
    """Hold an exclusive lock for one load-change-save of ``path``.

    The wait is bounded. A process that takes this lock and then wedges used to
    block every later run forever, with no output and no error: on 2026-10-04 one
    stuck holder sat for over two hours and every reply check behind it hung, which
    looked like the voice checker being broken rather than one stale process. After
    ``timeout`` seconds the lock is abandoned and the body runs unlocked, which is
    the same degradation this already accepts where ``fcntl`` is missing. Losing an
    interleaved write is recoverable; hanging the tool is not.

    Set ``PHERKAD_LOCK_TIMEOUT`` to change the bound, or 0 to wait forever.
    """
    if fcntl is None:
        yield
        return
    wait = LOCK_TIMEOUT if timeout is None else timeout
    lock_path = os.path.realpath(path) + ".lock"
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, "a") as fh:
        held = False
        if wait <= 0:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            held = True
        else:
            deadline = time.monotonic() + wait
            while True:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    held = True
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        print(f"statefile: gave up waiting {wait:g}s for {lock_path}; "
                              f"proceeding without the lock. A stale holder may be stuck.",
                              file=sys.stderr)
                        break
                    time.sleep(0.05)
        try:
            yield
        finally:
            if held:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
