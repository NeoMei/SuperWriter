#!/usr/bin/env python3
"""Regression tests for font-independent SVG geometry acceptance."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from svg_geometry_compare import SvgTextMaskError, masked_svg_pixels_match  # noqa: E402
from verify_acceptance import compare_pixels, normalized_pixels, validate_svg_source  # noqa: E402


class SvgGeometryComparisonTest(unittest.TestCase):
    def setUp(self):
        self.svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="200" '
            'viewBox="0 0 600 200">'
            '<rect width="600" height="200" fill="#ffffff"/>'
            '<rect x="80" y="55" width="440" height="100" rx="12" '
            'fill="#dceeff" stroke="#2468a2" stroke-width="4"/>'
            '<text x="300" y="122" text-anchor="middle" font-size="48" '
            'font-family="PingFang SC, sans-serif" fill="#17202a">MMMMMMMM</text>'
            '</svg>'
        )

    @staticmethod
    def _raster(*, text_scale: float = 1.0, include_text: bool = True,
                extra_shape: bool = False, text_fill: str = "#17202a") -> bytes:
        image = Image.new("RGB", (600, 200), "white")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (80, 55, 520, 155), radius=12, fill="#dceeff", outline="#2468a2", width=4
        )
        if extra_shape:
            draw.rectangle((8, 8, 72, 42), fill="#c00000")
        if include_text:
            font = ImageFont.load_default(size=48)
            layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
            layer_draw = ImageDraw.Draw(layer)
            layer_draw.text(
                (300, 122), "MMMMMMMM", font=font, fill=text_fill, anchor="ms"
            )
            if text_scale != 1.0:
                bounds = layer.getbbox()
                assert bounds is not None
                crop = layer.crop(bounds)
                crop = crop.resize(
                    (round(crop.width * text_scale), crop.height), Image.Resampling.BICUBIC
                )
                layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
                layer.alpha_composite(crop, (300 - crop.width // 2, bounds[1]))
            image = Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")
        output = io.BytesIO()
        image.save(output, format="PNG")
        with tempfile.TemporaryDirectory() as temporary:
            return normalized_pixels(
                output.getvalue(), "test SVG raster", Path(temporary), "test-svg"
            )

    def _source(self, directory: str, svg: str | None = None) -> Path:
        source = Path(directory) / "diagram.svg"
        source.write_text(svg or self.svg, encoding="utf-8")
        return source

    def test_fallback_accepts_controlled_alternate_font_metrics(self):
        accepted = self._raster(text_scale=1.0)
        alternate_font = self._raster(text_scale=1.35)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            compare_pixels(alternate_font, accepted, "strict comparison differs")
        with tempfile.TemporaryDirectory() as temporary:
            self.assertTrue(
                masked_svg_pixels_match(
                    self._source(temporary), alternate_font, accepted
                )
            )

    def test_fallback_rejects_shape_difference_outside_text_mask(self):
        accepted = self._raster(text_scale=1.0)
        changed_shape = self._raster(text_scale=1.35, extra_shape=True)
        with tempfile.TemporaryDirectory() as temporary:
            self.assertFalse(
                masked_svg_pixels_match(
                    self._source(temporary), changed_shape, accepted
                )
            )

    def test_fallback_rejects_missing_label_pixels(self):
        accepted = self._raster(text_scale=1.0)
        blank_label = self._raster(include_text=False)
        with tempfile.TemporaryDirectory() as temporary:
            self.assertFalse(
                masked_svg_pixels_match(
                    self._source(temporary), blank_label, accepted
                )
            )

    def test_blank_background_is_not_light_colored_label_ink(self):
        svg = self.svg.replace('#17202a', '#8899aa')
        with tempfile.TemporaryDirectory() as temporary:
            source = self._source(temporary, svg)
            self.assertFalse(masked_svg_pixels_match(
                source, self._raster(include_text=False), self._raster(text_fill="#8899aa")
            ))

    def test_fallback_rejects_unsupported_text_transform(self):
        transformed = self.svg.replace(
            '<text x="300"', '<g transform="translate(1 0)"><text x="300"'
        ).replace("</text></svg>", "</text></g></svg>")
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                SvgTextMaskError,
                r"SVG text mask is unsupported: text transforms are not supported",
            ):
                masked_svg_pixels_match(
                    self._source(temporary, transformed),
                    self._raster(text_scale=1.0),
                    self._raster(text_scale=1.0),
                )

    def test_fallback_rejects_css_or_inherited_text_layout(self):
        variants = {
            "style element": self.svg.replace(
                ">", '><style>text { font-size: 12px; }</style>', 1
            ),
            "ancestor style": self.svg.replace(
                '<text x="300"', '<g style="font-size:12px"><text x="300"'
            ).replace("</text></svg>", "</text></g></svg>"),
        }
        for name, svg in variants.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaisesRegex(
                    SvgTextMaskError,
                    r"SVG text mask is unsupported: CSS or inherited text layout is not supported",
                ):
                    masked_svg_pixels_match(
                        self._source(temporary, svg),
                        self._raster(text_scale=1.0),
                        self._raster(text_scale=1.0),
                    )

    def test_fallback_rejects_implicit_tspan_cursor_position(self):
        implicit = self.svg.replace(
            "MMMMMMMM</text>", "MMMM<tspan dy=\"40\">MMMM</tspan></text>"
        )
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                SvgTextMaskError,
                r"SVG text mask is unsupported: each tspan must declare x",
            ):
                masked_svg_pixels_match(
                    self._source(temporary, implicit),
                    self._raster(text_scale=1.0),
                    self._raster(text_scale=1.0),
                )

    def test_fallback_rejects_a_mask_that_hides_most_of_the_scene(self):
        oversized = self.svg.replace('font-size="48"', 'font-size="64"')
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                SvgTextMaskError,
                r"SVG text mask is unsupported: text regions cover too much of the image",
            ):
                masked_svg_pixels_match(
                    self._source(temporary, oversized),
                    self._raster(text_scale=1.0),
                    self._raster(text_scale=1.0),
                )

    def test_existing_semantic_validation_still_rejects_changed_label_text(self):
        changed = self.svg.replace(">MMMMMMMM</text>", ">changed</text>").replace(
            '<rect x="80" y="55" width="440" height="100" rx="12" ',
            '<g data-node-id="node"><rect x="80" y="55" width="440" height="100" rx="12" ',
        ).replace("</text></svg>", "</text></g></svg>")
        with tempfile.TemporaryDirectory() as temporary:
            source = self._source(temporary, changed)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
                validate_svg_source(
                    source,
                    {"node": "MMMMMMMM"},
                    [],
                    {"node": {"x": 80, "y": 55, "width": 440, "height": 100}},
                )
        self.assertIn("Excalidraw and SVG node labels differ", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
