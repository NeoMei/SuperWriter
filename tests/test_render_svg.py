from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zlib


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "render_svg.py"
SAMPLE = ROOT / "验收" / "模拟客户A" / "模拟标段1" / "配图" / "图1-国产化适配架构.svg"


def load_helper():
    spec = importlib.util.spec_from_file_location("superwriter_render_svg", HELPER)
    if spec is None or spec.loader is None:
        raise AssertionError("render_svg helper cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def valid_png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\xff"))
        + png_chunk(b"IEND", b"")
    )


class RenderSvgTest(unittest.TestCase):
    def test_real_resvg_renderer_produces_a_decodable_png(self):
        if importlib.util.find_spec("resvg_py") is None:
            self.skipTest("requires resvg-py")
        module = load_helper()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "render.png"
            backend = module.render_svg(SAMPLE, output)
            self.assertEqual(backend, "resvg")
            self.assertTrue(module._valid_png(output))

    def test_renderer_output_is_published_atomically(self):
        module = load_helper()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "render.png"
            output.write_bytes(b"previous-render")
            backend = module.render_svg(SAMPLE, output, renderer=lambda _: valid_png())
            self.assertEqual(backend, "resvg")
            self.assertEqual(output.read_bytes(), valid_png())
            self.assertEqual(list(root.glob(".render.png.*.tmp.png")), [])

    def test_invalid_renderer_output_is_rejected_and_preserves_existing_output(self):
        module = load_helper()
        invalid_payloads = {
            "header-only": valid_png()[:33],
            "bad-crc": valid_png()[:-1] + b"x",
            "not-png": b"not-a-png",
        }
        for case, payload in invalid_payloads.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                output = root / "render.png"
                output.write_bytes(b"previous-render")
                with self.assertRaisesRegex(
                    module.RenderSvgError,
                    r"^SVG rendering failed: resvg produced an invalid PNG$",
                ):
                    module.render_svg(SAMPLE, output, renderer=lambda _, p=payload: p)
                self.assertEqual(output.read_bytes(), b"previous-render")
                self.assertEqual(list(root.glob(".render.png.*.tmp.png")), [])

    def test_renderer_exception_has_stable_diagnostic_and_preserves_output(self):
        module = load_helper()

        def fail_renderer(_):
            raise ValueError("renderer internals")

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "render.png"
            output.write_bytes(b"previous-render")
            with self.assertRaisesRegex(
                module.RenderSvgError,
                r"^SVG rendering failed: resvg could not render the SVG$",
            ):
                module.render_svg(SAMPLE, output, renderer=fail_renderer)
            self.assertEqual(output.read_bytes(), b"previous-render")

    def test_missing_resvg_dependency_has_actionable_diagnostic(self):
        module = load_helper()
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(
            sys.modules, {"resvg_py": None}
        ), self.assertRaisesRegex(
            module.RenderSvgError,
            r"^SVG rendering requires resvg-py; install project requirements$",
        ):
            module.render_svg(SAMPLE, Path(temporary) / "render.png")

    def test_existing_output_must_be_a_regular_non_symlink_file(self):
        module = load_helper()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.png"
            target.write_bytes(b"target-bytes")
            linked = root / "linked.png"
            try:
                linked.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")
            directory = root / "directory.png"
            directory.mkdir()
            for output in (linked, directory):
                with self.assertRaisesRegex(
                    module.RenderSvgError,
                    r"^PNG output must be a regular non-symlink file when it exists$",
                ):
                    module.render_svg(SAMPLE, output, renderer=lambda _: valid_png())
            self.assertEqual(target.read_bytes(), b"target-bytes")

    def test_input_must_be_a_regular_non_symlink_svg(self):
        module = load_helper()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "render.png"
            directory = root / "directory.svg"
            directory.mkdir()
            with self.assertRaisesRegex(
                module.RenderSvgError,
                r"^SVG input must be a regular non-symlink \.svg file$",
            ):
                module.render_svg(directory, output, renderer=lambda _: valid_png())

            linked = root / "linked.svg"
            try:
                linked.symlink_to(SAMPLE)
            except OSError:
                return
            with self.assertRaisesRegex(
                module.RenderSvgError,
                r"^SVG input must be a regular non-symlink \.svg file$",
            ):
                module.render_svg(linked, output, renderer=lambda _: valid_png())

    def test_path_probe_errors_are_wrapped_without_touching_output(self):
        module = load_helper()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "render.png"
            output.write_bytes(b"previous-render")
            with mock.patch.object(
                module.Path, "resolve", side_effect=PermissionError("private-path")
            ), self.assertRaisesRegex(
                module.RenderSvgError,
                r"^SVG rendering path validation failed$",
            ):
                module.render_svg(SAMPLE, output, renderer=lambda _: valid_png())
            self.assertEqual(output.read_bytes(), b"previous-render")

    def test_output_filesystem_errors_are_wrapped_and_preserve_old_output(self):
        module = load_helper()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for case, failure in (
                ("mkstemp", mock.patch.object(module.tempfile, "mkstemp", side_effect=OSError)),
                ("chmod", mock.patch.object(module.Path, "chmod", side_effect=OSError)),
                ("replace", mock.patch.object(module.os, "replace", side_effect=OSError)),
            ):
                with self.subTest(case=case):
                    output = root / f"{case}.png"
                    output.write_bytes(b"previous-render")
                    with failure, self.assertRaisesRegex(
                        module.RenderSvgError,
                        r"^SVG rendering could not safely create or publish output$",
                    ):
                        module.render_svg(SAMPLE, output, renderer=lambda _: valid_png())
                    self.assertEqual(output.read_bytes(), b"previous-render")

    def test_cli_handles_unicode_paths_as_utf8(self):
        if importlib.util.find_spec("resvg_py") is None:
            self.skipTest("requires resvg-py")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "渲染结果.png"
            result = subprocess.run(
                [sys.executable, str(HELPER), str(SAMPLE), str(output)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "PASS: SVG rendered through resvg\n")
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
