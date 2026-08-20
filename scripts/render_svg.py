#!/usr/bin/env python3
"""Render an SVG to PNG with the macOS sips -> AppKit system chain."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import zlib


class RenderSvgError(RuntimeError):
    """Raised when the SVG system rendering chain cannot produce a valid PNG."""


def _valid_png(path: Path) -> bool:
    try:
        payload = path.read_bytes()
        if payload[:8] != b"\x89PNG\r\n\x1a\n":
            return False
        offset = 8
        ihdr: tuple[int, int, int, int] | None = None
        idat: list[bytes] = []
        palette_entries: int | None = None
        idat_ended = False
        saw_iend = False
        while offset < len(payload):
            if len(payload) - offset < 12:
                return False
            length = struct.unpack(">I", payload[offset : offset + 4])[0]
            end = offset + 12 + length
            if end > len(payload):
                return False
            kind = payload[offset + 4 : offset + 8]
            data = payload[offset + 8 : offset + 8 + length]
            expected_crc = struct.unpack(">I", payload[offset + 8 + length : end])[0]
            if len(kind) != 4 or any(
                byte not in range(ord("A"), ord("Z") + 1)
                and byte not in range(ord("a"), ord("z") + 1)
                for byte in kind
            ):
                return False
            if zlib.crc32(kind + data) & 0xFFFFFFFF != expected_crc:
                return False
            if kind == b"IHDR":
                if ihdr is not None or offset != 8 or length != 13:
                    return False
                width, height, bit_depth, color_type, compression, filtering, interlace = (
                    struct.unpack(">IIBBBBB", data)
                )
                legal_depths = {
                    0: {1, 2, 4, 8, 16},
                    2: {8, 16},
                    3: {1, 2, 4, 8},
                    4: {8, 16},
                    6: {8, 16},
                }
                if (
                    not 0 < width < 2**31
                    or not 0 < height < 2**31
                    or bit_depth not in legal_depths.get(color_type, set())
                    or compression != 0
                    or filtering != 0
                    or interlace != 0
                ):
                    return False
                ihdr = width, height, bit_depth, color_type
            elif ihdr is None:
                return False
            elif kind == b"PLTE":
                if palette_entries is not None or idat or length == 0 or length > 768 or length % 3:
                    return False
                color_type = ihdr[3]
                if color_type in {0, 4}:
                    return False
                palette_entries = length // 3
                if color_type == 3 and palette_entries > 2 ** ihdr[2]:
                    return False
            elif kind == b"IDAT":
                if idat_ended or saw_iend:
                    return False
                idat.append(data)
            elif kind == b"IEND":
                if length != 0 or not idat or end != len(payload):
                    return False
                saw_iend = True
            else:
                if idat:
                    idat_ended = True
                if kind[0] & 0x20 == 0:  # Unknown critical chunks are not decodable.
                    return False
            offset = end
            if saw_iend:
                break
        if ihdr is None or not saw_iend or offset != len(payload):
            return False
        width, height, bit_depth, color_type = ihdr
        if color_type == 3 and palette_entries is None:
            return False
        channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
        row_bytes = (width * channels * bit_depth + 7) // 8
        expected_size = height * (row_bytes + 1)
        if expected_size > 512 * 1024 * 1024:
            return False
        decompressor = zlib.decompressobj()
        decoded = decompressor.decompress(b"".join(idat), expected_size + 1)
        if len(decoded) > expected_size or decompressor.unconsumed_tail:
            return False
        decoded += decompressor.flush()
        if (
            not decompressor.eof
            or decompressor.unused_data
            or len(decoded) != expected_size
        ):
            return False
        return all(decoded[row * (row_bytes + 1)] <= 4 for row in range(height))
    except (OSError, KeyError, struct.error, ValueError, zlib.error):
        return False


def _temporary_output(output: Path) -> Path:
    descriptor, name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp.png", dir=str(output.parent)
    )
    os.close(descriptor)
    return Path(name)


def _run(command: list[str]) -> bool:
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def render_svg(
    source: Path | str,
    output: Path | str,
    *,
    sips_command: Path | str = "sips",
    osascript_command: Path | str = "osascript",
    jxa_script: Path | str | None = None,
) -> str:
    """Render *source* atomically to *output* and return ``sips`` or ``appkit``."""
    try:
        source_path = Path(source).expanduser().absolute()
        output_path = Path(output).expanduser().absolute()
        script_path = (
            Path(jxa_script).expanduser().absolute()
            if jxa_script is not None
            else Path(__file__).resolve().with_name("render_svg_macos.js")
        )

        try:
            source_mode = os.lstat(source_path).st_mode
        except FileNotFoundError:
            source_mode = None
        if (
            source_path.suffix.lower() != ".svg"
            or source_mode is None
            or not stat.S_ISREG(source_mode)
        ):
            raise RenderSvgError("SVG input must be a regular non-symlink .svg file")
        source_path = source_path.resolve(strict=True)
        if not source_path.is_file():
            raise RenderSvgError("SVG input must be a regular non-symlink .svg file")

        if output_path.suffix.lower() != ".png":
            raise RenderSvgError("PNG output must use an existing parent directory")
        resolved_parent = output_path.parent.resolve(strict=True)
        if not resolved_parent.is_dir():
            raise RenderSvgError("PNG output must use an existing parent directory")
        try:
            output_mode = os.lstat(output_path).st_mode
        except FileNotFoundError:
            output_mode = None
        if output_mode is not None and (
            stat.S_ISLNK(output_mode) or not stat.S_ISREG(output_mode)
        ):
            raise RenderSvgError(
                "PNG output must be a regular non-symlink file when it exists"
            )
        output_path = resolved_parent / output_path.name

        script_path = script_path.resolve(strict=True)
        if not script_path.is_file():
            raise RenderSvgError("AppKit SVG fallback script is unavailable")
    except RenderSvgError:
        raise
    except (OSError, RuntimeError):
        raise RenderSvgError("SVG rendering path validation failed") from None

    if source_path == output_path:
        raise RenderSvgError("SVG input and PNG output must be different files")

    try:
        output_mode = os.lstat(output_path).st_mode
    except FileNotFoundError:
        output_mode = None
    except OSError:
        raise RenderSvgError(
            "SVG rendering could not safely create or publish output"
        ) from None
    if output_mode is not None and (
        stat.S_ISLNK(output_mode) or not stat.S_ISREG(output_mode)
    ):
        raise RenderSvgError(
            "PNG output must be a regular non-symlink file when it exists"
        )
    try:
        temporary: Path | None = None
        try:
            temporary = _temporary_output(output_path)
            if _run(
                [
                    str(sips_command),
                    "-s",
                    "format",
                    "png",
                    str(source_path),
                    "--out",
                    str(temporary),
                ]
            ) and _valid_png(temporary):
                temporary.chmod(0o644)
                os.replace(temporary, output_path)
                temporary = None
                return "sips"

            temporary.unlink(missing_ok=True)
            temporary = None
            temporary = _temporary_output(output_path)
            if _run(
                [
                    str(osascript_command),
                    "-l",
                    "JavaScript",
                    str(script_path),
                    str(source_path),
                    str(temporary),
                ]
            ) and _valid_png(temporary):
                temporary.chmod(0o644)
                os.replace(temporary, output_path)
                temporary = None
                return "appkit"
            raise RenderSvgError(
                "SVG system rendering failed: sips and AppKit fallback both failed"
            )
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    except RenderSvgError:
        raise
    except OSError:
        raise RenderSvgError(
            "SVG rendering could not safely create or publish output"
        ) from None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="input SVG")
    parser.add_argument("output", type=Path, help="output PNG")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        backend = render_svg(args.source, args.output)
    except RenderSvgError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: SVG rendered through macOS {backend}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
