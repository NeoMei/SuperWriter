"""Compare SVG rasters outside bounded, font-dependent text regions."""

from __future__ import annotations

from collections import Counter
import math
from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET


NORMALIZED_WIDTH = 192
NORMALIZED_HEIGHT = 96
MAX_TEXT_MASK_RATIO = 0.35
MIN_UNMASKED_PIXELS = 1024


class SvgTextMaskError(ValueError):
    """The SVG uses text layout that cannot be masked safely."""


def _unsupported(message: str):
    raise SvgTextMaskError(f"SVG text mask is unsupported: {message}")


def _number(value: str | None, label: str) -> float:
    if value is None or not re.fullmatch(
        r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?", value.strip()
    ):
        _unsupported(f"{label} must be one finite unitless number")
    number = float(value)
    if not math.isfinite(number):
        _unsupported(f"{label} must be one finite unitless number")
    return number


def _text_width(text: str, font_size: float) -> float:
    units = 0.0
    for character in text:
        if character.isspace():
            units += 0.45
        elif unicodedata.east_asian_width(character) in {"W", "F", "A"}:
            units += 1.15
        elif character in "ilI.,:;!'|`":
            units += 0.45
        else:
            units += 1.05
    return max(font_size, units * font_size)


def _parse_color(value: str | None) -> tuple[int, int, int]:
    if value is None:
        _unsupported("each text line must declare a hexadecimal fill color")
    match = re.fullmatch(r"#([0-9a-fA-F]{6})", value.strip())
    if match is None:
        _unsupported("each text line must declare a six-digit hexadecimal fill color")
    encoded = match.group(1)
    return tuple(int(encoded[index:index + 2], 16) for index in (0, 2, 4))


def _layout(svg: Path):
    try:
        root = ET.parse(svg).getroot()
    except (OSError, ET.ParseError) as exc:
        _unsupported(f"SVG XML cannot be parsed ({exc})")
    namespace = root.tag.partition("}")[0].lstrip("{")
    if root.tag.rsplit("}", 1)[-1] != "svg" or not namespace:
        _unsupported("the root must be a namespaced SVG element")
    if set(root.attrib) != {"width", "height", "viewBox"}:
        _unsupported("CSS or inherited text layout is not supported")
    if any(node.tag.rsplit("}", 1)[-1] == "style" for node in root.iter()):
        _unsupported("CSS or inherited text layout is not supported")
    width = _number(root.get("width"), "root width")
    height = _number(root.get("height"), "root height")
    view_box = (root.get("viewBox") or "").replace(",", " ").split()
    if len(view_box) != 4:
        _unsupported("root viewBox must contain four finite unitless numbers")
    min_x, min_y, view_width, view_height = (
        _number(value, "root viewBox") for value in view_box
    )
    if width <= 0 or height <= 0 or view_width <= 0 or view_height <= 0:
        _unsupported("root dimensions and viewBox size must be positive")
    if abs(width / height - view_width / view_height) > 0.0001:
        _unsupported("root dimensions and viewBox must have the same aspect ratio")

    parent = {child: node for node in root.iter() for child in node}
    lines = []
    texts = root.findall(f".//{{{namespace}}}text")
    if not texts:
        _unsupported("at least one explicit text element is required")
    allowed_text = {
        "x", "y", "font-family", "font-size", "font-weight", "fill", "text-anchor",
    }
    allowed_tspan = {"x", "y", "dx", "dy", "font-size", "fill"}
    for text in texts:
        node = text
        while node is not root:
            if node.get("transform") is not None:
                _unsupported("text transforms are not supported")
            node = parent[node]
            if node is not root:
                if node.get("transform") is not None:
                    _unsupported("text transforms are not supported")
                if node.tag.rsplit("}", 1)[-1] != "g" or set(node.attrib) - {
                    "data-node-id", "data-edge-from", "data-edge-to",
                }:
                    _unsupported("CSS or inherited text layout is not supported")
        if set(text.attrib) - allowed_text:
            _unsupported("text attributes must use explicit simple positioning")
        x = _number(text.get("x"), "text x")
        y = _number(text.get("y"), "text y")
        font_size = _number(text.get("font-size"), "text font-size")
        if not 1 <= font_size <= view_height / 3:
            _unsupported("text font-size is outside the bounded range")
        anchor = text.get("text-anchor", "start")
        if anchor not in {"start", "middle", "end"}:
            _unsupported("text-anchor must be start, middle, or end")
        fill = _parse_color(text.get("fill"))
        children = list(text)
        if any(child.tag.rsplit("}", 1)[-1] != "tspan" for child in children):
            _unsupported("text may contain only simple tspan children")

        def add_line(content: str | None, line_x: float, line_y: float,
                     line_size: float, line_fill: tuple[int, int, int]):
            if content is None or not content.strip():
                return
            if any(unicodedata.category(character) == "Cc" for character in content):
                _unsupported("text contains control characters")
            text_width = _text_width(content, line_size)
            left = line_x if anchor == "start" else (
                line_x - text_width / 2 if anchor == "middle" else line_x - text_width
            )
            padding = max(2.0, line_size * 0.18)
            lines.append((
                left - padding,
                line_y - line_size * 1.12 - padding,
                left + text_width + padding,
                line_y + line_size * 0.32 + padding,
                line_fill,
            ))

        add_line(text.text, x, y, font_size, fill)
        current_x, current_y = x, y
        for tspan in children:
            if set(tspan.attrib) - allowed_tspan or list(tspan):
                _unsupported("tspan attributes must use explicit simple positioning")
            if tspan.tail and tspan.tail.strip():
                _unsupported("text after a tspan is not supported")
            if tspan.get("x") is None:
                _unsupported("each tspan must declare x")
            current_x = _number(tspan.get("x"), "tspan x")
            if tspan.get("y") is not None:
                current_y = _number(tspan.get("y"), "tspan y")
            if tspan.get("dx") is not None:
                current_x += _number(tspan.get("dx"), "tspan dx")
            if tspan.get("dy") is not None:
                current_y += _number(tspan.get("dy"), "tspan dy")
            line_size = (
                _number(tspan.get("font-size"), "tspan font-size")
                if tspan.get("font-size") is not None else font_size
            )
            if not 1 <= line_size <= view_height / 3:
                _unsupported("tspan font-size is outside the bounded range")
            line_fill = _parse_color(tspan.get("fill")) if tspan.get("fill") else fill
            add_line(tspan.text, current_x, current_y, line_size, line_fill)
    if not lines:
        _unsupported("at least one nonempty text line is required")
    return min_x, min_y, view_width, view_height, lines


def _mask(svg: Path):
    min_x, min_y, view_width, view_height, lines = _layout(svg)
    mask = bytearray(NORMALIZED_WIDTH * NORMALIZED_HEIGHT)
    regions = []
    for left, top, right, bottom, fill in lines:
        x0 = max(0, math.floor((left - min_x) * NORMALIZED_WIDTH / view_width))
        y0 = max(0, math.floor((top - min_y) * NORMALIZED_HEIGHT / view_height))
        x1 = min(NORMALIZED_WIDTH, math.ceil((right - min_x) * NORMALIZED_WIDTH / view_width))
        y1 = min(NORMALIZED_HEIGHT, math.ceil((bottom - min_y) * NORMALIZED_HEIGHT / view_height))
        if x1 <= x0 or y1 <= y0:
            _unsupported("a text region falls outside the rendered image")
        for y in range(y0, y1):
            start = y * NORMALIZED_WIDTH + x0
            mask[start:start + x1 - x0] = b"\1" * (x1 - x0)
        regions.append((x0, y0, x1, y1, fill))
    masked = sum(mask)
    total = len(mask)
    if masked / total > MAX_TEXT_MASK_RATIO:
        _unsupported("text regions cover too much of the image")
    if total - masked < MIN_UNMASKED_PIXELS:
        _unsupported("too little visible geometry remains outside text regions")
    return mask, regions


def _has_text_ink(pixels: bytes, region) -> bool:
    x0, y0, x1, y1, fill = region
    samples = [
        tuple(pixels[(y * NORMALIZED_WIDTH + x) * 3:(y * NORMALIZED_WIDTH + x) * 3 + 3])
        for y in range(y0, y1) for x in range(x0, x1)
    ]
    # Uniform region fill is background even when it is close to a pale label.
    background = Counter(samples).most_common(1)[0][0]
    matches = []
    for y in range(y0, y1):
        for x in range(x0, x1):
            offset = (y * NORMALIZED_WIDTH + x) * 3
            sample = pixels[offset:offset + 3]
            # Normalization downsamples large diagrams to 192x96. Thin CJK
            # strokes therefore become mostly antialiased blends rather than
            # exact fill-color pixels; keep the probe color-directed but allow
            # that bounded blend distance.
            fill_distance = max(abs(sample[i] - fill[i]) for i in range(3))
            background_distance = max(abs(sample[i] - background[i]) for i in range(3))
            if fill_distance <= 120 and background_distance >= 24:
                matches.append((x, y))
    area = (x1 - x0) * (y1 - y0)
    if len(matches) < max(2, math.ceil(area * 0.015)):
        return False
    return (
        max(x for x, _ in matches) - min(x for x, _ in matches) >= 2
        and max(y for _, y in matches) - min(y for _, y in matches) >= 1
    )


def masked_svg_pixels_match(svg: Path, rendered: bytes, approved: bytes) -> bool:
    """Compare normalized rasters outside safe text masks and require label ink."""
    expected_length = NORMALIZED_WIDTH * NORMALIZED_HEIGHT * 3
    if len(rendered) != expected_length or len(approved) != expected_length:
        return False
    mask, regions = _mask(svg)
    if not all(
        _has_text_ink(rendered, region) and _has_text_ink(approved, region)
        for region in regions
    ):
        return False
    rendered_geometry = bytearray()
    approved_geometry = bytearray()
    for index, masked in enumerate(mask):
        if not masked:
            offset = index * 3
            rendered_geometry.extend(rendered[offset:offset + 3])
            approved_geometry.extend(approved[offset:offset + 3])
    differences = [abs(left - right) for left, right in zip(rendered_geometry, approved_geometry)]
    mean_error = sum(differences) / len(differences)
    large_error_ratio = sum(value > 24 for value in differences) / len(differences)
    return mean_error <= 4.0 and large_error_ratio <= 0.02
