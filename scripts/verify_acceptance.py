#!/usr/bin/env python3
"""Validate one Superwriter project from its project-owned acceptance manifest."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path, label: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        fail(f"{label} is invalid: {exc}")


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
    return "".join(re.findall(r"[0-9A-Za-z\u3400-\u9fff]+", value)).casefold()


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


def bmp_pixels(path: Path, label: str) -> bytes:
    try:
        payload = path.read_bytes()
        if payload[:2] != b"BM":
            raise ValueError
        offset = struct.unpack_from("<I", payload, 10)[0]
        dib_size, width, height, planes, depth, compression = struct.unpack_from("<IiiHHI", payload, 14)
        if dib_size < 40 or width != 192 or abs(height) != 96 or planes != 1 or depth != 24 or compression != 0:
            raise ValueError
        stride = ((width * 3 + 3) // 4) * 4
        rows = []
        for row_index in range(abs(height)):
            row = payload[offset + row_index * stride:offset + row_index * stride + width * 3]
            if len(row) != width * 3:
                raise ValueError
            rows.append(bytes(channel for index in range(0, len(row), 3)
                              for channel in (row[index + 2], row[index + 1], row[index])))
        if height > 0:
            rows.reverse()
        return b"".join(rows)
    except (OSError, IndexError, struct.error, ValueError):
        fail(f"{label} sips output is unreadable")


def normalized_pixels(payload: bytes, label: str, directory: Path, stem: str) -> bytes:
    source = directory / f"{stem}.png"
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


def validate_figure(root: Path, item: object):
    if not isinstance(item, dict):
        fail("acceptance manifest figure entry is invalid")
    source = project_path(root, item.get("source"), "figure source")
    render = project_path(root, item.get("render"), "figure render")
    require_file(source, "missing native Excalidraw source")
    require_file(render, "missing rendered architecture diagram")
    caption = item.get("caption")
    nodes = item.get("nodes")
    edges = item.get("edges")
    if not isinstance(caption, str) or not caption or not isinstance(nodes, list) or not isinstance(edges, list):
        fail("acceptance manifest figure caption/topology is invalid")

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
    if sorted(actual_edges) != sorted(expected_edges):
        fail("Excalidraw directed topology/edge labels differ from manifest")
    if sha256(source) != item.get("source_sha256"):
        fail("Excalidraw source digest differs from acceptance manifest")

    render_payload = render.read_bytes()
    width, height = png_header(render_payload, "rendered architecture diagram")
    if not (100 <= width <= 20000 and 100 <= height <= 20000):
        fail("rendered architecture diagram dimensions are unreasonable")
    with tempfile.TemporaryDirectory(prefix="superwriter-render-") as temporary:
        pixels = normalized_pixels(render_payload, "rendered architecture diagram", Path(temporary), "render")
    if sha256(render) != item.get("render_sha256"):
        fail("rendered diagram digest differs from acceptance manifest")

    renderer = item.get("renderer")
    if renderer is not None:
        if not isinstance(renderer, list) or not renderer or not all(isinstance(part, str) for part in renderer):
            fail("acceptance manifest figure renderer is invalid")
        if shutil.which(renderer[0]):
            with tempfile.TemporaryDirectory(prefix="superwriter-renderer-") as temporary:
                output = Path(temporary) / "rendered.png"
                command = [part.replace("{source}", str(source)).replace("{output}", str(output)) for part in renderer]
                result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
                if result.returncode or not output.is_file():
                    fail("configured Excalidraw renderer failed")
                generated = output.read_bytes()
                png_header(generated, "renderer output")
                generated_pixels = normalized_pixels(generated, "renderer output", Path(temporary), "generated")
                compare_pixels(pixels, generated_pixels, "Excalidraw renderer output differs from accepted PNG")
    return source, render, caption, render_payload, width, height, pixels


def main() -> None:
    if len(sys.argv) != 2:
        fail("acceptance verifier requires one project directory")
    root = Path(sys.argv[1]).resolve()
    manifest_path = root / "验收清单.json"
    if not manifest_path.is_file():
        fail("acceptance manifest is missing: 验收清单.json")
    manifest = load_json(manifest_path, "acceptance manifest")
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
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

    if pipeline.get("completed_stage") != 9 or pipeline.get("human_gates") != [2, 5, 8] or pipeline.get("machine_gates") != [0, 3, 6, 7]:
        fail("acceptance manifest pipeline/gate contract is invalid")
    evidence = pipeline.get("stage_evidence")
    if not isinstance(evidence, list) or [entry.get("stage") for entry in evidence if isinstance(entry, dict)] != list(range(10)):
        fail("acceptance manifest must declare stage 0 through 9 evidence")
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
    for chapter in chapters:
        if not isinstance(chapter, dict) or not isinstance(chapter.get("number"), str) or not isinstance(chapter.get("points"), list):
            fail("acceptance manifest chapter entry is invalid")
        path = project_path(root, chapter.get("path"), "chapter path")
        require_file(path, f"required chapter is missing: {chapter.get('path')}")
        number = chapter["number"]
        declared_chapters[number] = path
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
    require_file(merged_path, "missing merged draft")
    require_file(docx_path, "missing DOCX delivery")
    require_file(pdf_path, "missing PDF delivery")
    if sha256(merged_path) != outputs.get("merged_sha256"):
        fail("merged draft digest differs from the generation manifest")
    placeholder = re.compile(r"【缺口|\b(?:TODO|TBD)\b|\{\{[^}\n]+\}\}|<客户|<标段", re.I)
    for path in [merged_path, *declared_chapters.values()]:
        if placeholder.search(path.read_text(encoding="utf-8")):
            fail(f"unresolved placeholder remains in accepted prose: {path.relative_to(root).as_posix()}")

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
    for figure_index, (_, _, caption, render_payload, width, height, render_pixels) in enumerate(validated_figures):
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
        embedded_width, embedded_height = png_header(embedded, "DOCX embedded diagram")
        if not (100 <= embedded_width <= 20000 and 100 <= embedded_height <= 20000):
            fail("DOCX embedded diagram dimensions are unreasonable")
        if abs((width / height) - (embedded_width / embedded_height)) / (width / height) > 0.002:
            fail("DOCX embedded diagram aspect ratio differs from the rendered diagram")
        with tempfile.TemporaryDirectory(prefix="superwriter-image-verify-") as temporary:
            embedded_pixels = normalized_pixels(embedded, "DOCX embedded diagram", Path(temporary), f"embedded-{figure_index}")
        compare_pixels(render_pixels, embedded_pixels, "DOCX embedded diagram pixels differ from the rendered diagram")

    docx_text = extracted_text("DOCX", docx_path)
    pdf_text = extracted_text("PDF", pdf_path)
    extracted = (("DOCX", docx_text), ("PDF", pdf_text))
    for label, text in extracted:
        for value in [*points, *terms, *(figure[2] for figure in validated_figures)]:
            if normalized(value) not in normalized(text):
                fail(f"{label} markitdown output is missing required text: {value}")
    for label, text in extracted:
        compact = normalized(text)
        for line in merged.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("!["):
                continue
            anchor = normalized(stripped)
            if len(anchor) >= 4 and anchor not in compact:
                fail(f"{label} content does not cover current merged draft: {stripped[:48]}")

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
    if not isinstance(minimum, int) or not isinstance(maximum, int) or minimum < 1 or maximum < minimum or not minimum <= pages <= maximum:
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
