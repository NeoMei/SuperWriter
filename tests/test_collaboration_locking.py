from __future__ import annotations

import builtins
import errno
import io
import unittest
from unittest import mock

from scripts.collaboration import locking


class _FakeMsvcrt:
    LK_NBLCK = 1
    LK_UNLCK = 2

    def __init__(self):
        self.calls = []

    def locking(self, descriptor, mode, size):
        self.calls.append((descriptor, mode, size))


class CollaborationLockingTest(unittest.TestCase):
    def test_windows_backend_locks_one_stable_byte_and_releases_it(self):
        fake = _FakeMsvcrt()
        real_import = builtins.__import__

        def import_module(name, *args, **kwargs):
            if name == "msvcrt":
                return fake
            return real_import(name, *args, **kwargs)

        handle = io.BytesIO()
        handle.fileno = lambda: 42
        with mock.patch("builtins.__import__", side_effect=import_module):
            locking.acquire(handle, platform="nt")
            locking.release(handle, platform="nt")

        self.assertEqual(handle.getvalue(), b"")
        self.assertEqual(fake.calls, [(42, fake.LK_NBLCK, 1), (42, fake.LK_UNLCK, 1)])

    def test_windows_backend_waits_for_contention_then_acquires(self):
        fake = _FakeMsvcrt()
        attempts = iter((OSError(errno.EACCES, "busy"), None))

        def locking_call(descriptor, mode, size):
            fake.calls.append((descriptor, mode, size))
            outcome = next(attempts)
            if outcome is not None:
                raise outcome

        fake.locking = locking_call
        real_import = builtins.__import__

        def import_module(name, *args, **kwargs):
            if name == "msvcrt":
                return fake
            return real_import(name, *args, **kwargs)

        handle = io.BytesIO(b"\0")
        handle.fileno = lambda: 42
        with mock.patch("builtins.__import__", side_effect=import_module), \
                mock.patch("scripts.collaboration.locking.time.sleep") as sleep:
            locking.acquire(handle, platform="nt")

        self.assertEqual(fake.calls, [(42, fake.LK_NBLCK, 1)] * 2)
        sleep.assert_called_once()

    def test_windows_backend_propagates_lock_failure(self):
        fake = _FakeMsvcrt()
        fake.locking = mock.Mock(side_effect=OSError("lock denied"))
        real_import = builtins.__import__

        def import_module(name, *args, **kwargs):
            if name == "msvcrt":
                return fake
            return real_import(name, *args, **kwargs)

        handle = io.BytesIO(b"\0")
        handle.fileno = lambda: 42
        with mock.patch("builtins.__import__", side_effect=import_module):
            with self.assertRaisesRegex(OSError, "lock denied"):
                locking.acquire(handle, platform="nt")
