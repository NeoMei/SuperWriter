#!/usr/bin/env python3
"""Focused tests for acceptance image contracts."""

from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_acceptance import (  # noqa: E402
    compare_pixels,
    figure_description_candidates,
    jpeg_header,
    markdown_block_sequence,
    normalized_pixels,
    pdf_metadata,
    require_ordered_export_coverage,
    require_ordered_source_coverage,
    validate_figure,
)


class AcceptanceImageContractTest(unittest.TestCase):
    def test_pillow_normalizes_png_and_jpeg_without_system_tools(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            image = Image.new("RGB", (32, 16), (20, 40, 60))
            png = io.BytesIO()
            image.save(png, format="PNG")
            jpeg = io.BytesIO()
            image.save(jpeg, format="JPEG", quality=100, subsampling=0)

            png_pixels = normalized_pixels(png.getvalue(), "PNG", directory, "png")
            jpeg_pixels = normalized_pixels(jpeg.getvalue(), "JPEG", directory, "jpeg", ".jpg")

            self.assertEqual(len(png_pixels), 192 * 96 * 3)
            compare_pixels(png_pixels, jpeg_pixels, "cross-format pixels differ")

    def test_palette_transparency_normalizes_like_equivalent_rgba(self):
        palette = Image.new("P", (32, 16), 0)
        palette.putpalette([0, 0, 0, 20, 40, 60] + [0] * 762)
        palette.paste(1, (8, 4, 24, 12))
        indexed = io.BytesIO()
        palette.save(indexed, format="PNG", transparency=0)
        with Image.open(io.BytesIO(indexed.getvalue())) as source:
            rgba = io.BytesIO()
            source.convert("RGBA").save(rgba, format="PNG")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.assertEqual(
                normalized_pixels(indexed.getvalue(), "indexed PNG", directory, "indexed"),
                normalized_pixels(rgba.getvalue(), "RGBA PNG", directory, "rgba"),
            )

    def test_pillow_rejects_an_invalid_declared_color_profile(self):
        image = Image.new("RGB", (32, 16), (20, 40, 60))
        png = io.BytesIO()
        image.save(png, format="PNG", icc_profile=b"invalid-profile")
        with tempfile.TemporaryDirectory() as temporary:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
                normalized_pixels(png.getvalue(), "rendered figure", Path(temporary), "bad")
        self.assertIn("has an invalid ICC color profile", stderr.getvalue())

    def test_markitdown_child_is_forced_to_utf8_under_a_legacy_locale(self):
        from unittest import mock
        from verify_acceptance import extracted_text

        real_run = subprocess.run

        def run_utf8_probe(_command, **kwargs):
            return real_run(
                [sys.executable, "-c", "print('中文内容')"],
                **kwargs,
            )

        with mock.patch.dict(
            os.environ,
            {"PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"},
        ), mock.patch(
            "verify_acceptance.subprocess.run", side_effect=run_utf8_probe
        ):
            self.assertEqual(extracted_text("DOCX", Path("中文.docx")), "中文内容\n")

    def test_missing_markitdown_has_a_stable_diagnostic(self):
        from unittest import mock
        from verify_acceptance import extracted_text

        stderr = io.StringIO()
        with mock.patch(
            "verify_acceptance.subprocess.run", side_effect=FileNotFoundError
        ), contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            extracted_text("DOCX", Path("delivery.docx"))
        self.assertIn("DOCX markitdown extraction failed", stderr.getvalue())

    def test_pillow_rejects_truncated_png_with_valid_header(self):
        payload = (
            b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13)
            + b"IHDR"
            + struct.pack(">IIBBBBB", 192, 96, 8, 2, 0, 0, 0)
            + b"\0\0\0\0"
        )
        with tempfile.TemporaryDirectory() as temporary:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
                normalized_pixels(payload, "rendered architecture diagram", Path(temporary), "bad")
        self.assertIn("is not a decodable image", stderr.getvalue())

    def test_pymupdf_reads_creator_page_count_and_a4_geometry(self):
        import fitz

        with tempfile.TemporaryDirectory() as temporary:
            pdf = Path(temporary) / "交付.pdf"
            with fitz.open() as document:
                document.set_metadata({"creator": "WPS Writer"})
                document.new_page(width=595.2756, height=841.8898)
                document.save(pdf)

            creator, page_sizes = pdf_metadata(pdf)

        self.assertEqual(creator, "WPS Writer")
        self.assertEqual(len(page_sizes), 1)
        self.assertAlmostEqual(page_sizes[0][0], 595.2756, places=2)
        self.assertAlmostEqual(page_sizes[0][1], 841.8898, places=2)

    def test_wps_frontmatter_control_fields_are_not_native_body_content(self):
        markdown = (
            "---\n"
            "title: 协作审阅试点技术方案（模拟验收）\n"
            "design: proposal\n"
            "caption_numbering: global\n"
            "heading_numbering: chinese-formal\n"
            "layout_engine: longform\n"
            "---\n\n"
            "# 审阅流程与追溯\n\n正文内容。\n"
            "\n# 异常处理与交付验收\n\n交付内容。\n"
        )

        blocks = markdown_block_sequence(markdown)
        self.assertEqual(blocks, [
            ("title", "协作审阅试点技术方案模拟验收"),
            ("heading chinese-formal h1", "审阅流程与追溯"),
            ("paragraph", "正文内容"),
            ("heading chinese-formal h1", "异常处理与交付验收"),
            ("paragraph", "交付内容"),
        ])
        require_ordered_source_coverage(
            "DOCX", "协作审阅试点技术方案（模拟验收） \n审阅流程与追溯 \n正文内容。 \n"
            "异常处理与交付验收 \n交付内容。", blocks
        )
        require_ordered_export_coverage(
            "PDF",
            "协作审阅试点技术方案（模拟验收）\n"
            "第一章 审阅流程与追溯\n正文内容。\n"
            "第二章 异常处理与交付验收\n交付内容。\n1\n",
            blocks,
            pdf_page_count=1,
        )
        require_ordered_export_coverage(
            "DOCX",
            "协作审阅试点技术方案（模拟验收）\n"
            "# 审阅流程与追溯\n正文内容。\n"
            "# 异常处理与交付验收\n交付内容。\n",
            blocks,
        )
        for bad_heading in (
            "第二章 审阅流程与追溯",
            "第一节 审阅流程与追溯",
            "项目第一章 审阅流程与追溯",
            "# 审阅流程与追溯",
            "# 第一章 审阅流程与追溯",
        ):
            export = (
                "协作审阅试点技术方案（模拟验收）\n"
                f"{bad_heading}\n正文内容。\n"
                "第二章 异常处理与交付验收\n交付内容。\n"
            )
            with self.subTest(bad_heading=bad_heading), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                require_ordered_export_coverage("PDF", export, blocks, pdf_page_count=1)
        for bad_footer in ("999", "1\n1"):
            export = (
                "协作审阅试点技术方案（模拟验收）\n"
                "第一章 审阅流程与追溯\n正文内容。\n"
                "第二章 异常处理与交付验收\n交付内容。\n"
                f"{bad_footer}\n"
            )
            with self.subTest(bad_footer=bad_footer), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                require_ordered_export_coverage("PDF", export, blocks, pdf_page_count=1)
        for changed in (
            "审阅流程与追溯 \n正文内容。",
            "被替换的可见标题 \n审阅流程与追溯 \n正文内容。",
        ):
            with self.subTest(changed=changed), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                require_ordered_source_coverage("DOCX", changed, blocks)

    def test_unknown_frontmatter_field_is_not_silently_ignored(self):
        self.assertEqual(
            markdown_block_sequence("---\ncustom_claim: 需要交付\n---\n\n# 正文\n"),
            [("paragraph", "customclaim需要交付"), ("heading", "正文")],
        )

    def test_wps_figure_directive_keeps_caption_and_ignores_only_control_fences(self):
        markdown = (
            "前文。\n\n"
            ':::figure {#fig:review-cycle caption="审阅记录确认循环" '
            'width="full" kind="diagram"}\n'
            "![图 1 审阅记录确认循环](配图/审阅记录确认循环.png)\n"
            ":::\n\n后文。\n"
        )

        self.assertEqual(markdown_block_sequence(markdown), [
            ("paragraph", "前文"),
            ("image caption", "图1审阅记录确认循环"),
            ("paragraph", "后文"),
        ])

    def test_unknown_directive_remains_substantive_source_content(self):
        self.assertEqual(
            markdown_block_sequence(":::warning\n不得忽略的内容\n:::\n"),
            [("paragraph", "warning不得忽略的内容")],
        )

    def test_public_figure_id_is_the_only_alternate_docx_description(self):
        markdown = (
            "---\n"
            "caption_numbering: global\n"
            "---\n"
            ':::figure {#fig:review-cycle caption="审阅记录确认循环" '
            'width="full" kind="diagram"}\n'
            "![图 1 审阅记录确认循环](配图/审阅记录确认循环.png)\n"
            ":::\n"
        )

        self.assertEqual(
            figure_description_candidates(markdown, "图 1 审阅记录确认循环"),
            {"fig:review-cycle"},
        )
        self.assertNotIn(
            "fig:other",
            figure_description_candidates(markdown, "图 1 审阅记录确认循环"),
        )
        self.assertEqual(
            figure_description_candidates(
                markdown.replace(
                    'caption="审阅记录确认循环"',
                    'caption="ALTERED VISIBLE CAPTION"',
                ),
                "图 1 审阅记录确认循环",
            ),
            {"图 1 审阅记录确认循环"},
        )
        self.assertEqual(
            figure_description_candidates(
                markdown.replace("图 1 审阅记录确认循环", "图 2 其他内容"),
                "图 1 审阅记录确认循环",
            ),
            {"图 1 审阅记录确认循环"},
        )

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

    def test_cross_format_pixel_comparison_allows_bounded_color_conversion(self):
        left = bytes(400)
        right = bytes([25] * 10 + [0] * 390)

        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            compare_pixels(left, right, "pixels differ")
        compare_pixels(
            left,
            right,
            "pixels differ",
            max_large_error_ratio=0.03,
        )


if __name__ == "__main__":
    unittest.main()
