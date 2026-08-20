from __future__ import annotations

import importlib.util
import io
from unittest import mock
from contextlib import redirect_stderr
import subprocess
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "render_svg.py"
JXA = ROOT / "scripts" / "render_svg_macos.js"
SAMPLE = ROOT / "验收" / "模拟客户A" / "模拟标段1" / "配图" / "图1-国产化适配架构.svg"


def load_helper():
    spec = importlib.util.spec_from_file_location("superwriter_render_svg", HELPER)
    if spec is None or spec.loader is None:
        raise AssertionError("render_svg helper cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_command(path: Path, body: str) -> Path:
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


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


def write_payload_command(path: Path, payload: bytes, returncode: int = 0) -> Path:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "import sys\n"
        f"Path(sys.argv[-1]).write_bytes(bytes.fromhex({payload.hex()!r}))\n"
        f"raise SystemExit({returncode})\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


class RenderSvgTest(unittest.TestCase):
    def test_helper_and_appkit_renderer_are_release_files(self):
        self.assertTrue(HELPER.is_file(), "scripts/render_svg.py is missing")
        self.assertTrue(JXA.is_file(), "scripts/render_svg_macos.js is missing")

    @unittest.skipUnless(HELPER.is_file() and JXA.is_file(), "renderer not implemented yet")
    def test_forced_sips_failure_falls_back_to_real_appkit(self):
        module = load_helper()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            failing_sips = write_command(root / "sips", "exit 13\n")
            output = root / "render.png"
            backend = module.render_svg(
                SAMPLE,
                output,
                sips_command=str(failing_sips),
                jxa_script=JXA,
            )
            self.assertEqual(backend, "appkit")
            self.assertTrue(output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    @unittest.skipUnless(HELPER.is_file() and JXA.is_file(), "renderer not implemented yet")
    def test_sips_rc_zero_with_invalid_png_falls_back_to_real_appkit(self):
        complete = valid_png()
        bad_crc = bytearray(complete)
        bad_crc[29] ^= 0x01
        idat_length = struct.unpack(">I", complete[33:37])[0]
        invalid_payloads = {
            "header-only": complete[:33],
            "bad-crc": bytes(bad_crc),
            "truncated-idat": complete[: 33 + 8 + max(1, idat_length // 2)],
        }
        module = load_helper()
        for case, payload in invalid_payloads.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fake_sips = write_payload_command(root / "sips", payload)
                output = root / "render.png"
                backend = module.render_svg(
                    SAMPLE,
                    output,
                    sips_command=str(fake_sips),
                    jxa_script=JXA,
                )
                self.assertEqual(backend, "appkit")
                self.assertNotEqual(output.read_bytes(), payload)
                self.assertTrue(output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    @unittest.skipUnless(HELPER.is_file() and JXA.is_file(), "renderer not implemented yet")
    def test_valid_sips_png_is_published_atomically_without_appkit(self):
        module = load_helper()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = valid_png()
            fake_sips = write_payload_command(root / "sips", payload)
            appkit_marker = root / "appkit-called"
            fake_osascript = write_command(
                root / "osascript", f"touch {str(appkit_marker)!r}\nexit 91\n"
            )
            output = root / "render.png"
            output.write_bytes(b"previous-render")

            backend = module.render_svg(
                SAMPLE,
                output,
                sips_command=str(fake_sips),
                osascript_command=str(fake_osascript),
                jxa_script=JXA,
            )

            self.assertEqual(backend, "sips")
            self.assertEqual(output.read_bytes(), payload)
            self.assertFalse(appkit_marker.exists(), "AppKit ran after a valid sips render")
            self.assertEqual(list(root.glob(".render.png.*.tmp.png")), [])

    @unittest.skipUnless(HELPER.is_file() and JXA.is_file(), "renderer not implemented yet")
    def test_both_backends_fail_with_stable_diagnostic_and_preserve_output(self):
        module = load_helper()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            failing_sips = write_command(root / "sips", "exit 13\n")
            failing_osascript = write_command(root / "osascript", "exit 17\n")
            output = root / "render.png"
            output.write_bytes(b"previous-render")
            with self.assertRaisesRegex(
                module.RenderSvgError,
                r"^SVG system rendering failed: sips and AppKit fallback both failed$",
            ):
                module.render_svg(
                    SAMPLE,
                    output,
                    sips_command=str(failing_sips),
                    osascript_command=str(failing_osascript),
                    jxa_script=JXA,
                )
            self.assertEqual(output.read_bytes(), b"previous-render")

    @unittest.skipUnless(HELPER.is_file() and JXA.is_file(), "renderer not implemented yet")
    def test_both_backends_return_invalid_png_and_preserve_output(self):
        module = load_helper()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            invalid = valid_png()[:33]
            fake_sips = write_payload_command(root / "sips", invalid)
            fake_osascript = write_payload_command(root / "osascript", invalid)
            output = root / "render.png"
            output.write_bytes(b"previous-render")
            with self.assertRaisesRegex(
                module.RenderSvgError,
                r"^SVG system rendering failed: sips and AppKit fallback both failed$",
            ):
                module.render_svg(
                    SAMPLE,
                    output,
                    sips_command=str(fake_sips),
                    osascript_command=str(fake_osascript),
                    jxa_script=JXA,
                )
            self.assertEqual(output.read_bytes(), b"previous-render")

    @unittest.skipUnless(HELPER.is_file() and JXA.is_file(), "renderer not implemented yet")
    def test_existing_output_must_be_a_regular_non_symlink_file(self):
        module = load_helper()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.png"
            target.write_bytes(b"target-bytes")
            symlink = root / "linked.png"
            symlink.symlink_to(target)
            directory = root / "directory.png"
            directory.mkdir()
            for case, output in (("symlink", symlink), ("directory", directory)):
                with self.subTest(case=case), self.assertRaisesRegex(
                    module.RenderSvgError,
                    r"^PNG output must be a regular non-symlink file when it exists$",
                ):
                    module.render_svg(SAMPLE, output, jxa_script=JXA)
            self.assertEqual(target.read_bytes(), b"target-bytes")

            cli = subprocess.run(
                ["python3", str(HELPER), str(SAMPLE), str(directory)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(cli.returncode, 1, cli.stdout + cli.stderr)
            self.assertIn(
                "FAIL: PNG output must be a regular non-symlink file when it exists",
                cli.stderr,
            )
            self.assertNotIn("Traceback", cli.stderr)

    @unittest.skipUnless(HELPER.is_file() and JXA.is_file(), "renderer not implemented yet")
    def test_input_must_be_a_regular_non_symlink_svg(self):
        module = load_helper()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "render.png"
            output.write_bytes(b"previous-render")
            linked = root / "linked.svg"
            linked.symlink_to(SAMPLE)
            directory = root / "directory.svg"
            directory.mkdir()
            for case, source in (("symlink", linked), ("directory", directory)):
                with self.subTest(case=case), self.assertRaisesRegex(
                    module.RenderSvgError,
                    r"^SVG input must be a regular non-symlink \.svg file$",
                ):
                    module.render_svg(source, output, jxa_script=JXA)
                self.assertEqual(output.read_bytes(), b"previous-render")
                self.assertEqual(list(root.glob(".render.png.*.tmp.png")), [])

    @unittest.skipUnless(HELPER.is_file() and JXA.is_file(), "renderer not implemented yet")
    def test_input_symlink_loops_are_stable_cli_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self_loop = root / "self.svg"
            self_loop.symlink_to(self_loop.name)
            chain_a = root / "chain-a.svg"
            chain_b = root / "chain-b.svg"
            chain_a.symlink_to(chain_b.name)
            chain_b.symlink_to(chain_a.name)
            for case, source in (("self", self_loop), ("chain", chain_a)):
                output = root / f"{case}.png"
                output.write_bytes(b"previous-render")
                result = subprocess.run(
                    ["python3", str(HELPER), str(source), str(output)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(
                    result.stderr,
                    "FAIL: SVG input must be a regular non-symlink .svg file\n",
                )
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(output.read_bytes(), b"previous-render")
                self.assertEqual(list(root.glob(f".{case}.png.*.tmp.png")), [])

    @unittest.skipUnless(HELPER.is_file() and JXA.is_file(), "renderer not implemented yet")
    def test_path_probe_permission_errors_are_wrapped_and_cli_has_no_traceback(self):
        module = load_helper()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "render.png"
            output.write_bytes(b"previous-render")
            for method in ("expanduser", "absolute", "resolve", "is_file", "is_dir"):
                with self.subTest(method=method), mock.patch.object(
                    module.Path, method, side_effect=PermissionError("private-path")
                ), self.assertRaisesRegex(
                    module.RenderSvgError,
                    r"^SVG rendering path validation failed$",
                ):
                    module.render_svg(SAMPLE, output, jxa_script=JXA)
                self.assertEqual(output.read_bytes(), b"previous-render")
                self.assertEqual(list(root.glob(".render.png.*.tmp.png")), [])

            resolved_sample = SAMPLE.resolve(strict=True)
            output_probe_cases = (
                (
                    "expanduser",
                    mock.patch.object(
                        module.Path,
                        "expanduser",
                        side_effect=[Path(SAMPLE), PermissionError("private-output")],
                    ),
                ),
                (
                    "absolute",
                    mock.patch.object(
                        module.Path,
                        "absolute",
                        side_effect=[Path(SAMPLE), PermissionError("private-output")],
                    ),
                ),
                (
                    "resolve",
                    mock.patch.object(
                        module.Path,
                        "resolve",
                        side_effect=[resolved_sample, PermissionError("private-output")],
                    ),
                ),
            )
            for method, failure in output_probe_cases:
                with self.subTest(output_method=method), failure, self.assertRaisesRegex(
                    module.RenderSvgError,
                    r"^SVG rendering path validation failed$",
                ):
                    module.render_svg(SAMPLE, output, jxa_script=JXA)
                self.assertEqual(output.read_bytes(), b"previous-render")
                self.assertEqual(list(root.glob(".render.png.*.tmp.png")), [])

            stderr = io.StringIO()
            with mock.patch.object(
                module.Path, "resolve", side_effect=PermissionError("private-path")
            ), mock.patch.object(
                sys, "argv", [str(HELPER), str(SAMPLE), str(output)]
            ), redirect_stderr(stderr):
                returncode = module.main()
            self.assertEqual(returncode, 1)
            self.assertEqual(stderr.getvalue(), "FAIL: SVG rendering path validation failed\n")
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertEqual(output.read_bytes(), b"previous-render")

    @unittest.skipUnless(HELPER.is_file() and JXA.is_file(), "renderer not implemented yet")
    def test_output_filesystem_errors_are_wrapped_and_preserve_old_output(self):
        module = load_helper()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            failing_sips = write_command(root / "sips", "exit 13\n")
            cases = (
                ("mkstemp", mock.patch.object(module.tempfile, "mkstemp", side_effect=OSError)),
                ("chmod", mock.patch.object(module.Path, "chmod", side_effect=OSError)),
                ("replace", mock.patch.object(module.os, "replace", side_effect=OSError)),
            )
            for case, failure in cases:
                with self.subTest(case=case):
                    output = root / f"{case}.png"
                    output.write_bytes(b"previous-render")
                    with failure, self.assertRaisesRegex(
                        module.RenderSvgError,
                        r"^SVG rendering could not safely create or publish output$",
                    ):
                        module.render_svg(
                            SAMPLE,
                            output,
                            sips_command=str(failing_sips),
                            jxa_script=JXA,
                        )
                    self.assertEqual(output.read_bytes(), b"previous-render")

    @unittest.skipUnless(JXA.is_file(), "renderer not implemented yet")
    def test_jxa_rejects_missing_arguments(self):
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", str(JXA)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("requires exactly one SVG input and one PNG output", result.stdout)


if __name__ == "__main__":
    unittest.main()
