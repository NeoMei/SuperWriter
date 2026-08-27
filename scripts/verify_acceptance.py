#!/usr/bin/env python3
"""Validate one Superwriter project from its project-owned acceptance manifest."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import struct
import subprocess
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

from render_svg import RenderSvgError, render_svg


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_json(path: Path, label: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)
    except (OSError, UnicodeError, ValueError) as exc:
        fail(f"{label} is invalid: {exc}")


def require_keys(value: object, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        fail(f"{label} has unknown or missing keys")


def valid_digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def is_json_integer(value: object) -> bool:
    return type(value) is int


def project_path(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or "\0" in value or "\n" in value:
        fail(f"acceptance manifest {label} must be a non-empty relative path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        fail(f"acceptance manifest {label} escapes the project directory")
    path = root.joinpath(*pure.parts)
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        fail(f"acceptance manifest {label} escapes the project directory")
    return path


def require_file(path: Path, message: str) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        fail(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def markdown_rows(text: str):
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and re.fullmatch(r"[A-Za-z]+\d+", cells[0]):
            yield cells


def normalized(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", value).casefold()
        if unicodedata.category(character)[0] in {"L", "M", "N", "S"} or character == "\u200d"
    )


def markdown_block_sequence(text: str):
    blocks = []
    paragraph = []

    def append(kind: str, source: str) -> None:
        value = normalized(source)
        if source.strip() and not value:
            fail(f"canonical merged draft {kind} has no synchronized Unicode content")
        if value:
            blocks.append((kind, value))

    def flush_paragraph() -> None:
        if paragraph:
            append("paragraph", " ".join(paragraph))
            paragraph.clear()

    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            flush_paragraph()
            continue
        if re.fullmatch(r"(?:-{3,}|\*{3,}|_{3,})", stripped):
            flush_paragraph()
            continue
        heading = re.match(r"^#{1,6}\s*(.*)$", stripped)
        if heading:
            flush_paragraph()
            append("heading", heading.group(1))
            continue
        image = re.fullmatch(r"!\[([^]]*)\]\([^)]*\)", stripped)
        if image:
            flush_paragraph()
            append("image caption", image.group(1))
            continue
        if stripped.startswith("|"):
            flush_paragraph()
            if not re.fullmatch(r"[|:\- ]+", stripped):
                cells = [cell.strip() for cell in stripped.strip("|").split("|") if cell.strip()]
                append("table row", " ".join(cells))
            continue
        paragraph.append(stripped)
    flush_paragraph()
    return blocks


def require_ordered_source_coverage(label: str, text: str, source_blocks) -> None:
    compact = normalized_export_text(text)
    cursor = 0
    for kind, block in source_blocks:
        position = compact.find(block, cursor)
        if position < 0:
            fail(f"{label} content does not cover current merged draft in order ({kind}): {block[:48]}")
        cursor = position + len(block)


def require_ordered_export_coverage(label: str, text: str, source_blocks) -> None:
    paragraphs = [value for kind, value in source_blocks if kind == "paragraph"]
    if not paragraphs:
        fail("canonical merged draft has no substantive paragraphs")
    first_paragraph = paragraphs[0]
    headings = [value for kind, value in source_blocks if kind == "heading"]
    source_compact = "".join(value for _, value in source_blocks)
    cursor = 0
    started = False
    for kind, content, original, table_wrapped in export_lines(text):
        if kind in {"page", "separator", "image"}:
            continue
        if kind == "toc":
            if started:
                fail(f"{label} contains an unexpected table-of-contents marker in body text")
            continue
        body = normalized(content)
        if not body:
            continue  # Unicode punctuation and spacing are explicitly folded.
        wrapped_heading = recognized_export_heading(content, table_wrapped, headings)
        if wrapped_heading is not None:
            body = wrapped_heading
        if not started:
            if wrapped_heading is not None:
                continue
            if body not in first_paragraph:
                fail(f"{label} contains unrecognized content before the first canonical merged-draft paragraph: {original[:48]}")
            started = True
        position = source_compact.find(body, cursor)
        if position < 0:
            fail(f"{label} contains substantive body text absent or out of order in canonical merged draft: {original[:48]}")
        cursor = position + len(body)
    if not started:
        fail(f"{label} content does not contain the first canonical merged-draft paragraph")


def recognized_export_heading(content: str, table_wrapped: bool, headings) -> str | None:
    candidate = content.strip()
    candidate = re.sub(r"^#{1,6}\s*", "", candidate)
    if table_wrapped:
        candidate = re.sub(r"^第(?:[一二三四五六七八九十百]+|\d+)节\s*", "", candidate)
    value = normalized(candidate)
    if value in headings:
        return value
    toc_candidate = re.sub(r"(?:\.{2,}|…{2,}|\s+)\d+\s*$", "", candidate)
    value = normalized(toc_candidate)
    return value if value in headings else None


def export_lines(text: str):
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if re.fullmatch(r"Page\s*\d+", stripped, re.I):
            yield "page", "", raw.strip(), False
            continue
        if stripped == "目 录":
            yield "toc", "", raw.strip(), False
            continue
        if re.fullmatch(r"!\[[^]]*\]\(data:image/[^;\s)]+;base64(?:,[^)]*|\.\.\.)\)", stripped, re.I):
            yield "image", "", raw.strip(), False
            continue
        table_wrapped = stripped.startswith("|") and stripped.endswith("|")
        if table_wrapped:
            if re.fullmatch(r"[|:\- .]+", stripped):
                yield "separator", "", raw.strip(), True
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|") if cell.strip()]
            content = " ".join(cells)
        else:
            content = stripped
        yield "content", content, raw.strip(), table_wrapped


def normalized_export_text(text: str) -> str:
    return "".join(normalized(content) for kind, content, _, _ in export_lines(text)
                   if kind == "content")


def extracted_text(label: str, path: Path) -> str:
    result = subprocess.run(
        ["markitdown", str(path)], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False,
    )
    if result.returncode:
        fail(f"{label} markitdown extraction failed")
    return result.stdout


def png_header(payload: bytes, label: str):
    try:
        if len(payload) < 33 or payload[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError
        if struct.unpack(">I", payload[8:12])[0] != 13 or payload[12:16] != b"IHDR":
            raise ValueError
        width, height = struct.unpack(">II", payload[16:24])
        if not width or not height:
            raise ValueError
        return width, height
    except (struct.error, ValueError):
        fail(f"{label} does not have a valid PNG header")


def jpeg_header(payload: bytes, label: str):
    """Return JPEG dimensions without requiring Pillow."""
    try:
        if len(payload) < 4 or payload[:2] != b"\xff\xd8":
            raise ValueError
        offset = 2
        sof_markers = {
            0xC0, 0xC1, 0xC2, 0xC3,
            0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB,
            0xCD, 0xCE, 0xCF,
        }
        while offset < len(payload):
            if payload[offset] != 0xFF:
                raise ValueError
            while offset < len(payload) and payload[offset] == 0xFF:
                offset += 1
            if offset >= len(payload):
                raise ValueError
            marker = payload[offset]
            offset += 1
            if marker in {0x01, *range(0xD0, 0xDA)}:
                continue
            if offset + 2 > len(payload):
                raise ValueError
            length = struct.unpack(">H", payload[offset:offset + 2])[0]
            if length < 2 or offset + length > len(payload):
                raise ValueError
            if marker in sof_markers:
                if length < 7:
                    raise ValueError
                height, width = struct.unpack(">HH", payload[offset + 3:offset + 7])
                if not width or not height:
                    raise ValueError
                return width, height
            if marker in {0xD9, 0xDA}:
                break
            offset += length
        raise ValueError
    except (IndexError, struct.error, ValueError):
        fail(f"{label} does not have a valid JPEG header")


def bmp_pixels(path: Path, label: str) -> bytes:
    try:
        payload = path.read_bytes()
        if payload[:2] != b"BM":
            raise ValueError
        offset = struct.unpack_from("<I", payload, 10)[0]
        dib_size, width, height, planes, depth, compression = struct.unpack_from("<IiiHHI", payload, 14)
        if dib_size < 40 or width != 192 or abs(height) != 96 or planes != 1 or (depth, compression) not in {(24, 0), (32, 3)}:
            raise ValueError
        channels = depth // 8
        stride = ((width * channels + 3) // 4) * 4
        rows = []
        for row_index in range(abs(height)):
            row = payload[offset + row_index * stride:offset + row_index * stride + width * channels]
            if len(row) != width * channels:
                raise ValueError
            rows.append(bytes(channel for index in range(0, len(row), channels)
                              for channel in (row[index + 2], row[index + 1], row[index])))
        if height > 0:
            rows.reverse()
        return b"".join(rows)
    except (OSError, IndexError, struct.error, ValueError):
        fail(f"{label} sips output is unreadable")


def normalized_pixels(
    payload: bytes,
    label: str,
    directory: Path,
    stem: str,
    suffix: str = ".png",
) -> bytes:
    source = directory / f"{stem}{suffix}"
    output = directory / f"{stem}.bmp"
    source.write_bytes(payload)
    result = subprocess.run(
        ["sips", "-m", "/System/Library/ColorSync/Profiles/sRGB Profile.icc",
         "-s", "format", "bmp", "-z", "96", "192", str(source), "--out", str(output)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if result.returncode or not output.is_file():
        fail(f"{label} is not decodable by sips")
    return bmp_pixels(output, label)


def compare_pixels(left: bytes, right: bytes, message: str) -> None:
    differences = [abs(a - b) for a, b in zip(left, right)]
    if not differences:
        fail(message)
    mean_error = sum(differences) / len(differences)
    large_error_ratio = sum(value > 24 for value in differences) / len(differences)
    if mean_error > 4.0 or large_error_ratio > 0.02:
        fail(message)


def excalidraw_scene(source: Path):
    try:
        text = source.read_text(encoding="utf-8")
        match = re.search(r"```json\n(.*?)\n```", text, re.S)
        if match is None:
            fail("native Excalidraw source is missing its JSON block")
        return json.loads(match.group(1))["elements"]
    except (OSError, KeyError, TypeError, ValueError) as exc:
        fail(f"native Excalidraw JSON is invalid: {exc}")


def svg_path_endpoints(value: str):
    token_pattern = r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"
    tokens = re.findall(token_pattern, value)
    if not tokens or re.sub(token_pattern, "", value).replace(",", "").strip():
        fail("SVG edge path data is invalid")
    arities = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7}
    index = 0
    command = None
    current = (0.0, 0.0)
    first = None
    subpath_start = None
    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            command = token
            index += 1
            if command.upper() == "Z":
                if subpath_start is None:
                    fail("SVG edge path closes before it starts")
                current = subpath_start
                command = None
                continue
        if command is None:
            fail("SVG edge path data is invalid")
        upper = command.upper()
        arity = arities[upper]
        if index + arity > len(tokens) or any(item.isalpha() for item in tokens[index:index + arity]):
            fail("SVG edge path data is invalid")
        numbers = [float(item) for item in tokens[index:index + arity]]
        if not all(math.isfinite(item) for item in numbers):
            fail("SVG edge path data is invalid")
        index += arity
        relative = command.islower()
        if upper == "H":
            endpoint = (current[0] + numbers[0] if relative else numbers[0], current[1])
        elif upper == "V":
            endpoint = (current[0], current[1] + numbers[0] if relative else numbers[0])
        else:
            x, y = numbers[-2:]
            endpoint = (current[0] + x, current[1] + y) if relative else (x, y)
        if upper == "M":
            if first is not None:
                fail("SVG edge path must contain one connected subpath")
            first = endpoint
            subpath_start = endpoint
            command = "l" if relative else "L"
        current = endpoint
    if first is None or current == first:
        fail("SVG edge path endpoints are invalid")
    return first, current


def svg_edge_endpoints(group, namespace: str):
    primitives = [child for child in group if child.tag.rsplit("}", 1)[-1] in {"line", "path"}]
    if len(primitives) != 1:
        fail("each SVG edge must contain exactly one visible line or path")
    primitive = primitives[0]
    if group.get("transform") or primitive.get("transform"):
        fail("SVG edge transforms are unsupported")
    kind = primitive.tag.rsplit("}", 1)[-1]
    try:
        if kind == "line":
            start = (float(primitive.get("x1")), float(primitive.get("y1")))
            end = (float(primitive.get("x2")), float(primitive.get("y2")))
        else:
            start, end = svg_path_endpoints(primitive.get("d") or "")
    except (TypeError, ValueError):
        fail("SVG edge coordinates are invalid")
    if not all(math.isfinite(value) for point in (start, end) for value in point) or start == end:
        fail("SVG edge coordinates are invalid")
    return primitive, start, end


def near_rectangle_boundary(point, rectangle) -> bool:
    x, y = point
    left, top = float(rectangle["x"]), float(rectangle["y"])
    right = left + float(rectangle["width"])
    bottom = top + float(rectangle["height"])
    tolerance = max(4.0, min(right - left, bottom - top) * 0.05)
    if not (left - tolerance <= x <= right + tolerance and top - tolerance <= y <= bottom + tolerance):
        return False
    distance = min(abs(x - left), abs(x - right), abs(y - top), abs(y - bottom))
    return distance <= tolerance


def validate_svg_source(svg: Path, expected_nodes, expected_edges, rectangles):
    try:
        root = ET.parse(svg).getroot()
    except (OSError, ET.ParseError) as exc:
        fail(f"SVG render source is invalid: {exc}")
    namespace = root.tag.partition("}")[0].lstrip("{")
    if root.tag.rsplit("}", 1)[-1] != "svg" or not namespace:
        fail("SVG render source root is invalid")
    groups = root.findall(f".//{{{namespace}}}g")
    svg_nodes = {}
    for group in groups:
        node_id = group.get("data-node-id")
        if not node_id:
            continue
        rect = group.find(f"{{{namespace}}}rect")
        text = group.find(f"{{{namespace}}}text")
        if rect is None or text is None:
            fail(f"SVG node geometry/label is missing: {node_id}")
        try:
            box = tuple(float(rect.get(name)) for name in ("x", "y", "width", "height"))
        except (TypeError, ValueError):
            fail(f"SVG node geometry is invalid: {node_id}")
        svg_nodes[node_id] = (box, "".join(text.itertext()))
    if set(svg_nodes) != set(expected_nodes):
        fail("Excalidraw and SVG node IDs differ")
    for node_id, label in expected_nodes.items():
        source = rectangles[node_id]
        source_box = tuple(float(source[name]) for name in ("x", "y", "width", "height"))
        svg_box, svg_label = svg_nodes[node_id]
        if any(abs(left - right) > 0.01 for left, right in zip(source_box, svg_box)):
            fail(f"Excalidraw and SVG node geometry differ: {node_id}")
        if normalized(svg_label) != normalized(label):
            fail(f"Excalidraw and SVG node labels differ: {node_id}")
    svg_edges = []
    edge_primitives = set()
    for group in groups:
        start, end = group.get("data-edge-from"), group.get("data-edge-to")
        if not start and not end:
            continue
        text = group.find(f"{{{namespace}}}text")
        if not start or not end or text is None:
            fail("SVG directed topology/edge label is invalid")
        primitive, visible_start, visible_end = svg_edge_endpoints(group, namespace)
        edge_primitives.add(id(primitive))
        if start not in rectangles or end not in rectangles:
            fail("SVG edge metadata references an unknown node")
        if not near_rectangle_boundary(visible_start, rectangles[start]):
            fail("SVG edge start is not near its declared source node boundary")
        if not near_rectangle_boundary(visible_end, rectangles[end]):
            fail("SVG edge end is not near its declared target node boundary")
        svg_edges.append((start, end, "".join(text.itertext())))
    if len(svg_edges) != len(set(svg_edges)):
        fail("SVG contains duplicate directed edges")
    if sorted(svg_edges) != sorted(expected_edges):
        fail("Excalidraw and SVG directed topology/edge labels differ")
    parent = {child: node for node in root.iter() for child in node}
    for primitive in root.findall(f".//{{{namespace}}}line") + root.findall(f".//{{{namespace}}}path"):
        ancestors = []
        node = primitive
        while node in parent:
            node = parent[node]
            ancestors.append(node.tag.rsplit("}", 1)[-1])
        if id(primitive) not in edge_primitives and not any(name in {"defs", "marker", "clipPath", "mask"} for name in ancestors):
            fail("SVG contains an unbound visible edge primitive")


def validate_figure(root: Path, item: object):
    """Validate a figure entry, supporting both ai-image-to-ppt and excalidraw formats."""
    if not isinstance(item, dict):
        fail("acceptance manifest figure entry is invalid")

    is_excalidraw = "source" in item
    if is_excalidraw:
        require_keys(
            item,
            {
                "source", "render_source", "render", "caption",
                "source_sha256", "render_source_sha256", "render_sha256",
                "nodes", "edges",
            },
            "acceptance manifest figure",
        )
    else:
        require_keys(
            item,
            {"render", "caption", "render_sha256"},
            "acceptance manifest figure",
        )

    caption = item.get("caption")
    render = project_path(root, item.get("render"), "figure render")
    figure_label = "rendered architecture diagram" if is_excalidraw else "rendered figure"
    require_file(render, f"missing {figure_label}")
    if not isinstance(caption, str) or not caption:
        fail("acceptance manifest figure caption is invalid")
    if not valid_digest(item.get("render_sha256")):
        fail("acceptance manifest figure render digest is invalid")

    if is_excalidraw:
        # Excalidraw format validation
        source = project_path(root, item.get("source"), "figure source")
        render_source = project_path(root, item.get("render_source"), "figure render source")
        require_file(source, "missing native Excalidraw source")
        require_file(render_source, "missing SVG render source")
        nodes = item.get("nodes")
        edges = item.get("edges")
        if not isinstance(nodes, list) or not isinstance(edges, list):
            fail("acceptance manifest figure nodes/edges are invalid for excalidraw format")
        for node in nodes:
            require_keys(node, {"id", "label"}, "acceptance manifest figure node")
        for edge in edges:
            require_keys(edge, {"from", "to", "label"}, "acceptance manifest figure edge")
        if not all(valid_digest(item.get(name)) for name in ("source_sha256", "render_source_sha256")):
            fail("acceptance manifest figure source digests are invalid")

        elements = excalidraw_scene(source)
        expected_nodes = {node.get("id"): node.get("label") for node in nodes if isinstance(node, dict)}
        if len(expected_nodes) != len(nodes) or any(not key or not isinstance(value, str) for key, value in expected_nodes.items()):
            fail("acceptance manifest figure nodes are invalid")
        rectangles = {element.get("id"): element for element in elements if element.get("type") == "rectangle"}
        arrows = [element for element in elements if element.get("type") == "arrow"]
        if set(rectangles) != set(expected_nodes):
            fail(f"native Excalidraw must contain exactly {len(nodes)} declared rectangle elements")
        if len(arrows) != len(edges):
            fail(f"native Excalidraw must contain exactly {len(edges)} declared arrow elements")

        boxes = []
        for node_id, label in expected_nodes.items():
            rectangle = rectangles[node_id]
            try:
                x, y = float(rectangle["x"]), float(rectangle["y"])
                width, height = float(rectangle["width"]), float(rectangle["height"])
            except (KeyError, TypeError, ValueError):
                fail("Excalidraw node geometry is invalid")
            if width <= 0 or height <= 0:
                fail("Excalidraw node geometry is invalid")
            for other_id, left, top, right, bottom in boxes:
                if x < right and x + width > left and y < bottom and y + height > top:
                    fail(f"Excalidraw node geometry overlaps: {other_id} and {node_id}")
            boxes.append((node_id, x, y, x + width, y + height))
            labels = [element for element in elements if element.get("type") == "text" and element.get("containerId") == node_id]
            if len(labels) != 1 or labels[0].get("text", labels[0].get("originalText")) != label:
                fail(f"Excalidraw node label differs from manifest: {node_id}")

        actual_edges = []
        for arrow in arrows:
            start, end = arrow.get("startBinding"), arrow.get("endBinding")
            if not isinstance(start, dict) or not isinstance(end, dict):
                fail("every Excalidraw arrow must have startBinding and endBinding")
            endpoints = (rectangles.get(start.get("elementId")), rectangles.get(end.get("elementId")))
            if None in endpoints:
                fail("every Excalidraw arrow binding must reference a rectangle endpoint")
            for endpoint in endpoints:
                ids = {bound.get("id") for bound in endpoint.get("boundElements", []) if isinstance(bound, dict)}
                if arrow.get("id") not in ids:
                    fail("Excalidraw arrow endpoints must list the arrow in boundElements")
            labels = [element.get("text", element.get("originalText")) for element in elements
                      if element.get("type") == "text" and element.get("containerId") == arrow.get("id")]
            actual_edges.append((start.get("elementId"), end.get("elementId"), labels[0] if len(labels) == 1 else None))
        expected_edges = [(edge.get("from"), edge.get("to"), edge.get("label")) for edge in edges if isinstance(edge, dict)]
        if len(expected_edges) != len(edges) or any(not all(isinstance(value, str) and value for value in edge) for edge in expected_edges):
            fail("acceptance manifest figure edges are invalid")
        if sorted(actual_edges) != sorted(expected_edges):
            fail("Excalidraw directed topology/edge labels differ from manifest")
        validate_svg_source(render_source, expected_nodes, expected_edges, rectangles)
        if sha256(source) != item.get("source_sha256"):
            fail("Excalidraw source digest differs from acceptance manifest")
        if sha256(render_source) != item.get("render_source_sha256"):
            fail("SVG render source digest differs from acceptance manifest")

    render_payload = render.read_bytes()
    render_suffix = render.suffix.lower()
    if is_excalidraw:
        width, height = png_header(render_payload, figure_label)
        normalization_suffix = ".png"
    elif render_suffix == ".png":
        width, height = png_header(render_payload, figure_label)
        normalization_suffix = ".png"
    elif render_suffix in {".jpg", ".jpeg"}:
        width, height = jpeg_header(render_payload, figure_label)
        normalization_suffix = ".jpg"
    else:
        fail("ai-image-to-ppt figure render must be PNG or JPEG")
    if not (100 <= width <= 20000 and 100 <= height <= 20000):
        fail(f"{figure_label} dimensions are unreasonable")

    with tempfile.TemporaryDirectory(prefix="superwriter-render-") as temporary:
        pixels = normalized_pixels(
            render_payload,
            figure_label,
            Path(temporary),
            "render",
            normalization_suffix,
        )
    if sha256(render) != item.get("render_sha256"):
        fail("rendered figure digest differs from acceptance manifest")

    if is_excalidraw:
        with tempfile.TemporaryDirectory(prefix="superwriter-svg-render-") as temporary:
            directory = Path(temporary)
            svg_png = directory / "svg.png"
            try:
                render_svg(render_source, svg_png)
            except RenderSvgError as exc:
                fail(str(exc))
            svg_payload = svg_png.read_bytes()
            png_header(svg_payload, "SVG raster")
            svg_pixels = normalized_pixels(svg_payload, "SVG raster", directory, "svg-normalized")
        compare_pixels(svg_pixels, pixels, "SVG raster differs from accepted PNG")

    return source if is_excalidraw else render, render, caption, render_payload, width, height, pixels


def main() -> None:
    if len(sys.argv) != 2:
        fail("acceptance verifier requires one project directory")
    root = Path(sys.argv[1]).resolve()
    manifest_path = root / "验收清单.json"
    if not manifest_path.is_file():
        fail("acceptance manifest is missing: 验收清单.json")
    manifest = load_json(manifest_path, "acceptance manifest")
    require_keys(manifest, {"version", "points", "required_terms", "pipeline", "chapters", "point_chapters", "figures", "outputs", "pdf"}, "acceptance manifest")
    if not isinstance(manifest, dict) or not is_json_integer(manifest.get("version")):
        fail("acceptance manifest integer fields must use JSON integers")
    if manifest.get("version") != 1:
        fail("acceptance manifest version is unsupported")

    points = manifest.get("points")
    terms = manifest.get("required_terms")
    pipeline = manifest.get("pipeline")
    chapters = manifest.get("chapters")
    point_chapters = manifest.get("point_chapters")
    figures = manifest.get("figures")
    outputs = manifest.get("outputs")
    pdf_contract = manifest.get("pdf")
    if not isinstance(points, list) or not points or len(points) != len(set(points)) or not all(re.fullmatch(r"[A-Za-z]+\d+", str(point)) for point in points):
        fail("acceptance manifest point IDs are invalid")
    if not isinstance(terms, list) or not all(isinstance(term, str) and term for term in terms):
        fail("acceptance manifest required terms are invalid")
    if not all(isinstance(value, dict) for value in (pipeline, point_chapters, outputs, pdf_contract)) or not isinstance(chapters, list) or not isinstance(figures, list):
        fail("acceptance manifest structure is invalid")
    require_keys(pipeline, {"status", "score_table", "matrix", "outline", "completed_stage", "human_gates", "machine_gates", "stage_evidence"}, "acceptance manifest pipeline")
    require_keys(outputs, {"merged", "merged_sha256", "docx", "pdf"}, "acceptance manifest outputs")
    require_keys(pdf_contract, {"min_pages", "max_pages", "page_size"}, "acceptance manifest pdf")
    if len(terms) != len(set(terms)):
        fail("acceptance manifest required terms must be unique")
    if set(point_chapters) != set(points):
        fail("acceptance manifest point_chapters keys must equal point IDs")
    if not valid_digest(outputs.get("merged_sha256")):
        fail("acceptance manifest merged digest is invalid")

    human_gates = pipeline.get("human_gates")
    machine_gates = pipeline.get("machine_gates")
    evidence = pipeline.get("stage_evidence")
    integer_scalars = (pipeline.get("completed_stage"), pdf_contract.get("min_pages"), pdf_contract.get("max_pages"))
    if (not all(is_json_integer(value) for value in integer_scalars)
            or not isinstance(human_gates, list)
            or not all(is_json_integer(value) for value in human_gates)
            or not isinstance(machine_gates, list)
            or not all(is_json_integer(value) for value in machine_gates)
            or (isinstance(evidence, list)
                and any(isinstance(entry, dict) and not is_json_integer(entry.get("stage")) for entry in evidence))):
        fail("acceptance manifest integer fields must use JSON integers")

    if pipeline.get("completed_stage") != 9 or human_gates != [2, 5, 8] or machine_gates != [0, 3, 6, 7]:
        fail("acceptance manifest pipeline/gate contract is invalid")
    if not isinstance(evidence, list) or [entry.get("stage") for entry in evidence if isinstance(entry, dict)] != list(range(10)):
        fail("acceptance manifest must declare stage 0 through 9 evidence")
    for entry in evidence:
        require_keys(entry, {"stage", "path"}, "acceptance manifest stage evidence")
    evidence_paths = [entry["path"] for entry in evidence]
    if len(evidence_paths) != len(set(evidence_paths)):
        fail("acceptance manifest stage evidence paths must be unique")
    for entry in evidence:
        path = project_path(root, entry.get("path"), f"stage {entry.get('stage')} evidence")
        require_file(path, f"required pipeline evidence is missing for stage {entry.get('stage')}: {entry.get('path')}")

    status_path = project_path(root, pipeline.get("status"), "pipeline status")
    score_path = project_path(root, pipeline.get("score_table"), "score table")
    matrix_path = project_path(root, pipeline.get("matrix"), "matrix")
    outline_path = project_path(root, pipeline.get("outline"), "outline")
    for path in (status_path, score_path, matrix_path, outline_path):
        require_file(path, f"required pipeline evidence is missing: {path.relative_to(root).as_posix()}")
    status = status_path.read_text(encoding="utf-8")
    if not re.search(r"当前阶段[：:]\s*9\s*[（(]?完成", status):
        fail("pipeline status does not record stage 9 complete")
    gate_line = next((line for line in status.splitlines() if "流程门" in line), "")
    recorded_gates = {int(number) for number in re.findall(r"\d+", gate_line)}
    for gate in [0, 2, 3, 5, 6, 7, 8]:
        if gate not in recorded_gates:
            fail(f"pipeline status is missing gate {gate} evidence")
    human_count = re.search(r"人工介入[：:]\s*(\d+)\s*次", status)
    if human_count is None or int(human_count.group(1)) != 3:
        fail("pipeline status must record exactly three human interventions")

    score_rows = list(markdown_rows(score_path.read_text(encoding="utf-8")))
    matrix_rows = list(markdown_rows(matrix_path.read_text(encoding="utf-8")))
    score_ids = [row[0] for row in score_rows]
    matrix_ids = [row[0] for row in matrix_rows]
    if score_ids != points or matrix_ids != points or len(score_ids) != len(matrix_ids):
        fail("score-table count, matrix count, and manifest point IDs differ")
    if len(matrix_ids) != len(set(matrix_ids)):
        fail("matrix point mappings are not unique")
    for row in matrix_rows:
        if len(row) < 7 or not row[4] or row[4] in {"—", "-"} or row[6] != "已核查":
            fail(f"matrix point is not uniquely assigned and checked: {row[0]}")
        if str(point_chapters.get(row[0])) != row[4]:
            fail(f"matrix primary chapter differs from manifest: {row[0]}")
    matrix_text = matrix_path.read_text(encoding="utf-8")
    if not re.search(rf"已映射[：:]\s*{len(points)}\s*/\s*{len(points)}", matrix_text) or "100%" not in matrix_text and "全覆盖" not in matrix_text:
        fail("matrix does not record 100% checked coverage")

    outline = outline_path.read_text(encoding="utf-8")
    declared_chapters = {}
    declared_chapter_paths = set()
    for chapter in chapters:
        require_keys(chapter, {"number", "path", "points"}, "acceptance manifest chapter")
        if not isinstance(chapter, dict) or not isinstance(chapter.get("number"), str) or not isinstance(chapter.get("points"), list):
            fail("acceptance manifest chapter entry is invalid")
        path = project_path(root, chapter.get("path"), "chapter path")
        require_file(path, f"required chapter is missing: {chapter.get('path')}")
        number = chapter["number"]
        if len(chapter["points"]) != len(set(chapter["points"])):
            fail(f"acceptance manifest chapter points must be unique: {chapter.get('path')}")
        relative_path = path.relative_to(root).as_posix()
        if number in declared_chapters or relative_path in declared_chapter_paths:
            fail("acceptance manifest chapter numbers and paths must be unique")
        declared_chapters[number] = path
        declared_chapter_paths.add(relative_path)
        chapter_text = path.read_text(encoding="utf-8")
        if not re.search(rf"(?m)^#+\s*{re.escape(number)}\.", chapter_text):
            fail(f"chapter file heading does not match chapter number: {chapter.get('path')}")
        for point in chapter["points"]:
            if point not in points or point not in chapter_text:
                fail(f"chapter point mapping is missing: {chapter.get('path')} -> {point}")
    for point, number in point_chapters.items():
        if point not in points or str(number) not in declared_chapters:
            fail(f"outline/chapter mapping is invalid: {point}")
        if point not in outline or not re.search(rf"(?m)^\s*{re.escape(str(number))}\.\s+.*{re.escape(point)}", outline):
            fail(f"outline is missing primary chapter mapping: {point} -> {number}")

    merged_path = project_path(root, outputs.get("merged"), "merged draft")
    docx_path = project_path(root, outputs.get("docx"), "DOCX output")
    pdf_path = project_path(root, outputs.get("pdf"), "PDF output")
    canonical_merged = (root / "合并稿.md").resolve()
    if outputs.get("merged") != "合并稿.md" or merged_path.resolve() != canonical_merged:
        fail("outputs.merged must be the canonical project-root 合并稿.md")
    if project_path(root, evidence[7].get("path"), "stage 7 evidence").resolve() != canonical_merged:
        fail("stage 7 evidence must be the canonical project-root 合并稿.md")
    delivery_root = (root / "导出").resolve()
    if docx_path.parent.resolve() != delivery_root or docx_path.suffix.lower() != ".docx":
        fail("DOCX output must be a .docx directly under 导出/")
    if pdf_path.parent.resolve() != delivery_root or pdf_path.suffix.lower() != ".pdf":
        fail("PDF output must be a .pdf directly under 导出/")
    if project_path(root, evidence[9].get("path"), "stage 9 evidence").resolve() != docx_path.resolve():
        fail("stage 9 evidence must be the declared DOCX output")
    require_file(merged_path, "missing merged draft")
    require_file(docx_path, "missing DOCX delivery")
    require_file(pdf_path, "missing PDF delivery")
    if sha256(merged_path) != outputs.get("merged_sha256"):
        fail("merged draft digest differs from the generation manifest")
    placeholder = re.compile(r"【缺口|\b(?:TODO|TBD)\b|\{\{[^}\n]+\}\}|<客户|<标段", re.I)
    for path in [merged_path, *declared_chapters.values()]:
        if placeholder.search(path.read_text(encoding="utf-8")):
            fail(f"unresolved placeholder remains in accepted prose: {path.relative_to(root).as_posix()}")

    figure_paths = []
    for figure in figures:
        if isinstance(figure, dict):
            # Support both excalidraw (source, render_source, render) and ai-image-to-ppt (render only)
            paths = [figure.get("render")]
            if "source" in figure:
                paths.extend([figure.get("source"), figure.get("render_source")])
            figure_paths.extend(p for p in paths if p)
    if len(figure_paths) != len(set(figure_paths)):
        fail("acceptance manifest figure paths must be unique")
    validated_figures = [validate_figure(root, figure) for figure in figures]
    merged = merged_path.read_text(encoding="utf-8")
    for _, render, caption, *_ in validated_figures:
        if render.relative_to(root).as_posix() not in merged or caption not in merged:
            fail(f"merged draft does not reference declared figure/caption: {caption}")

    try:
        with zipfile.ZipFile(docx_path) as archive:
            app = ET.fromstring(archive.read("docProps/app.xml"))
            document = ET.fromstring(archive.read("word/document.xml"))
            relationships = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
            names = set(archive.namelist())
    except (OSError, KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
        fail(f"DOCX metadata is unreadable: {exc}")
    application = next((element.text or "" for element in app if element.tag.rsplit("}", 1)[-1] == "Application"), "")
    if "WPS Office" not in application:
        fail("DOCX Application must contain WPS Office")
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main",
          "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
          "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
          "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"}
    for figure_index, (_, render, caption, render_payload, width, height, render_pixels) in enumerate(validated_figures):
        matches = []
        for drawing in document.findall(".//w:drawing", ns):
            docpr = drawing.find(".//wp:docPr", ns)
            cnvpr = drawing.find(".//pic:cNvPr", ns)
            if docpr is not None and cnvpr is not None and docpr.get("descr") == caption and cnvpr.get("descr") == caption:
                matches.append(drawing)
        if len(matches) != 1:
            fail("DOCX expected diagram caption/description is missing")
        ids = [element.get(f"{{{ns['r']}}}embed") for element in matches[0].findall(".//a:blip", ns)]
        ids = [item for item in ids if item]
        if len(ids) != 1:
            fail("DOCX expected diagram relationship is missing")
        relationship = next((element for element in relationships if element.get("Id") == ids[0]), None)
        if relationship is None or not relationship.get("Type", "").endswith("/image"):
            fail("DOCX expected diagram relationship is missing")
        member = posixpath.normpath(posixpath.join("word", relationship.get("Target", "")))
        if member.startswith("../") or not member.startswith("word/media/") or member not in names:
            fail("DOCX expected diagram relationship target is missing")
        with zipfile.ZipFile(docx_path) as archive:
            embedded = archive.read(member)
        if embedded.startswith(b"\x89PNG\r\n\x1a\n"):
            embedded_width, embedded_height = png_header(embedded, "DOCX embedded diagram")
            embedded_suffix = ".png"
        elif embedded.startswith(b"\xff\xd8"):
            embedded_width, embedded_height = jpeg_header(embedded, "DOCX embedded diagram")
            embedded_suffix = ".jpg"
        elif render.suffix.lower() == ".png":
            embedded_width, embedded_height = png_header(embedded, "DOCX embedded diagram")
            embedded_suffix = ".png"
        else:
            embedded_width, embedded_height = jpeg_header(embedded, "DOCX embedded diagram")
            embedded_suffix = ".jpg"
        if not (100 <= embedded_width <= 20000 and 100 <= embedded_height <= 20000):
            fail("DOCX embedded diagram dimensions are unreasonable")
        if abs((width / height) - (embedded_width / embedded_height)) / (width / height) > 0.002:
            fail("DOCX embedded diagram aspect ratio differs from the rendered diagram")
        with tempfile.TemporaryDirectory(prefix="superwriter-image-verify-") as temporary:
            embedded_pixels = normalized_pixels(
                embedded,
                "DOCX embedded diagram",
                Path(temporary),
                f"embedded-{figure_index}",
                embedded_suffix,
            )
        compare_pixels(render_pixels, embedded_pixels, "DOCX embedded diagram pixels differ from the rendered diagram")

    docx_text = extracted_text("DOCX", docx_path)
    pdf_text = extracted_text("PDF", pdf_path)
    extracted = (("DOCX", docx_text), ("PDF", pdf_text))
    source_blocks = markdown_block_sequence(merged)
    if not source_blocks:
        fail("canonical merged draft has no substantive content")
    for label, text in extracted:
        compact = normalized_export_text(text)
        for value in [*points, *terms, *(figure[2] for figure in validated_figures)]:
            if normalized(value) not in compact:
                fail(f"{label} markitdown output is missing required text: {value}")
    for label, text in extracted:
        require_ordered_source_coverage(label, text, source_blocks)
        require_ordered_export_coverage(label, text, source_blocks)

    metadata = subprocess.run(["pdfinfo", str(pdf_path)], text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, check=False)
    if metadata.returncode:
        fail("PDF metadata is unreadable")
    if not re.search(r"^Creator:\s+.*WPS", metadata.stdout, re.M):
        fail("PDF Creator must contain WPS")
    page_match = re.search(r"^Pages:\s+(\d+)$", metadata.stdout, re.M)
    if page_match is None or int(page_match.group(1)) <= 0:
        fail("PDF delivery must contain at least one page")
    pages = int(page_match.group(1))
    minimum, maximum = pdf_contract.get("min_pages"), pdf_contract.get("max_pages")
    if not is_json_integer(minimum) or not is_json_integer(maximum) or minimum < 1 or maximum < minimum or not minimum <= pages <= maximum:
        fail("PDF delivery page count violates acceptance manifest constraints")
    if pdf_contract.get("page_size") != "A4":
        fail("acceptance manifest PDF page size must be A4")
    for page in range(1, pages + 1):
        detail = subprocess.run(["pdfinfo", "-f", str(page), "-l", str(page), str(pdf_path)],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        if detail.returncode or not re.search(rf"^Page\s+{page}\s+size:\s+.*\(A4\)$", detail.stdout, re.M):
            fail(f"PDF delivery page {page} must be A4")

    print(f"PASS: explicit acceptance manifest and artifacts at {root} are satisfied")


if __name__ == "__main__":
    main()
