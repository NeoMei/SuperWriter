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

from verify_acceptance import (  # noqa: E402
    compare_pixels,
    figure_description_candidates,
    jpeg_header,
    markdown_block_sequence,
    require_ordered_export_coverage,
    require_ordered_source_coverage,
    validate_figure,
)


class AcceptanceImageContractTest(unittest.TestCase):
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
