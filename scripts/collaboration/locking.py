"""Portable blocking advisory locks for collaboration state transactions."""

from __future__ import annotations

import errno
import os
import time
from typing import BinaryIO


_WINDOWS_RETRY_SECONDS = 0.05


def acquire(handle: BinaryIO, *, platform: str | None = None) -> None:
    """Wait until an exclusive lock is held for this open file handle."""
    selected = os.name if platform is None else platform
    if selected == "nt":
        import msvcrt

        handle.seek(0)
        while True:
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError as error:
                if error.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise
                time.sleep(_WINDOWS_RETRY_SECONDS)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def release(handle: BinaryIO, *, platform: str | None = None) -> None:
    """Release a lock previously acquired by :func:`acquire`."""
    selected = os.name if platform is None else platform
    if selected == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
