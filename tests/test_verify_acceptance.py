#!/usr/bin/env python3
"""Focused tests for acceptance image contracts."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
import struct
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_acceptance import jpeg_header, validate_figure  # noqa: E402


class AcceptanceImageContractTest(unittest.TestCase):
    def test_jpeg_header_reads_sof_dimensions_without_pillow(self):
        payload = (
            b"\xff\xd8"
            b"\xff\xe0\x00\x04AB"
            b"\xff\xc0\x00\x11\x08"
            + struct.pack(">HH", 360, 640)
            + b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00"
            + b"\xff\xd9"
        )

        self.assertEqual(jpeg_header(payload, "rendered figure"), (640, 360))

    def test_ai_image_figure_rejects_unknown_renderer_key_even_when_null(self):
        with tempfile.TemporaryDirectory() as temporary:
            error = io.StringIO()
            with contextlib.redirect_stderr(error), self.assertRaises(SystemExit):
                validate_figure(
                    Path(temporary),
                    {
                        "render": "figure.jpg",
                        "caption": "Figure 1",
                        "render_sha256": "0" * 64,
                        "renderer": None,
                    },
                )

        self.assertIn(
            "acceptance manifest figure has unknown or missing keys",
            error.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
