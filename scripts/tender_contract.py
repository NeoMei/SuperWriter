"""Validation and deterministic derived views for tender response contracts."""

from __future__ import annotations

import re
import unicodedata


class TenderContractError(ValueError):
    """Raised when a source-bound tender declaration is malformed."""


def _dict(value: object, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict):
        raise TenderContractError(f"{label} must be an object")
    unknown = set(value) - fields
    missing = fields - set(value)
    if unknown:
        raise TenderContractError(f"{label} has unknown field: {sorted(unknown)[0]}")
    if missing:
        raise TenderContractError(f"{label} is missing field: {sorted(missing)[0]}")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise TenderContractError(f"{label} must be a trimmed nonempty string")
    if "\n" in value or "\r" in value:
        raise TenderContractError(f"{label} must be one line")
    return value


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TenderContractError(f"{label} must be a positive integer")
    return value


def _unique_strings(value: object, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list):
        raise TenderContractError(f"{label} must be a list")
    result = []
    for item in value:
        if not isinstance(item, str):
            raise TenderContractError(f"{label} must contain strings")
        if not item or (not allow_empty and not item.strip()):
            raise TenderContractError(f"{label} must not contain empty strings")
        if item != item.strip():
            raise TenderContractError(f"{label} must be trimmed strings")
        result.append(item)
    if len(result) != len(set(result)):
        raise TenderContractError(f"{label} must contain unique values")
    return result


def normalize_label(value: str) -> str:
    """Normalize spacing/punctuation for comparison while retaining source labels."""
    if not isinstance(value, str):
        raise TenderContractError("label must be a string")
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


def validate_tender_contract(value: object) -> None:
    """Validate the syntax and internal references of a tender contract."""
    contract = _dict(
        value,
        {"source_locator", "structure_mode", "sections", "scoring_items", "review_index"},
        "tender_contract",
    )
    _text(contract["source_locator"], "tender_contract source_locator")
    if contract["structure_mode"] not in {"fixed", "partial", "free"}:
        raise TenderContractError("tender_contract structure_mode is invalid")

    sections = contract["sections"]
    if not isinstance(sections, list) or not sections:
        raise TenderContractError("tender_contract sections must be a nonempty list")
    section_ids: set[str] = set()
    section_by_id: dict[str, dict] = {}
    orders = []
    for section in sections:
        row = _dict(
            section,
            {"id", "title", "order", "kind", "parent", "allow_extensions"},
            "tender section",
        )
        identifier = _text(row["id"], "tender section id")
        if identifier in section_ids:
            raise TenderContractError("tender section ids must be unique")
        section_ids.add(identifier)
        section_by_id[identifier] = row
        _text(row["title"], f"tender section {identifier} title")
        order = _positive_int(row["order"], f"tender section {identifier} order")
        orders.append(order)
        if row["kind"] not in {"volume", "chapter", "table", "attachment"}:
            raise TenderContractError(f"tender section {identifier} kind is invalid")
        if row["parent"] is not None and not isinstance(row["parent"], str):
            raise TenderContractError(f"tender section {identifier} parent is invalid")
        if not isinstance(row["allow_extensions"], bool):
            raise TenderContractError(f"tender section {identifier} allow_extensions is invalid")
    if sorted(orders) != list(range(1, len(orders) + 1)):
        raise TenderContractError("tender section order must be contiguous")
    for identifier, row in section_by_id.items():
        if row["parent"] is not None and row["parent"] not in section_ids:
            raise TenderContractError(f"tender section {identifier} parent is unknown")

    scoring_items = contract["scoring_items"]
    if not isinstance(scoring_items, list) or not scoring_items:
        raise TenderContractError("tender_contract scoring_items must be a nonempty list")
    item_ids: set[str] = set()
    item_orders = []
    for item in scoring_items:
        row = _dict(
            item,
            {"id", "label", "source_label", "order", "section_id", "evidence_ids", "aliases"},
            "tender scoring item",
        )
        identifier = _text(row["id"], "tender scoring item id")
        if identifier in item_ids:
            raise TenderContractError("tender scoring item ids must be unique")
        item_ids.add(identifier)
        _text(row["label"], f"tender scoring item {identifier} label")
        _text(row["source_label"], f"tender scoring item {identifier} source_label")
        item_orders.append(_positive_int(row["order"], f"tender scoring item {identifier} order"))
        if row["section_id"] not in section_ids:
            raise TenderContractError(f"tender scoring item {identifier} section is unknown")
        _unique_strings(row["evidence_ids"], f"tender scoring item {identifier} evidence_ids")
        _unique_strings(row["aliases"], f"tender scoring item {identifier} aliases")
    if sorted(item_orders) != list(range(1, len(item_orders) + 1)):
        raise TenderContractError("tender scoring item order must be contiguous")

    index = _dict(
        contract["review_index"],
        {"section_id", "required_item_ids", "rows"},
        "tender review_index",
    )
    if index["section_id"] not in section_ids:
        raise TenderContractError("tender review_index section is unknown")
    required = _unique_strings(index["required_item_ids"], "tender review_index required_item_ids")
    if set(required) != item_ids:
        raise TenderContractError("tender review_index required_item_ids must match scoring_items")
    if not isinstance(index["rows"], list):
        raise TenderContractError("tender review_index rows must be a list")
    for row in index["rows"]:
        item_row = _dict(row, {"item_id", "label", "page", "notes"}, "tender review_index row")
        _text(item_row["item_id"], "tender review_index row item_id")
        _text(item_row["label"], "tender review_index row label")
        if item_row["page"] is not None and (
            isinstance(item_row["page"], bool)
            or not isinstance(item_row["page"], int)
            or item_row["page"] <= 0
        ):
            raise TenderContractError("tender review_index row page must be null or positive integer")
        _text(item_row["notes"], "tender review_index row notes") if item_row["notes"] else None

    # Fixed/prescribed sections remain source-bound. A score item can use one
    # only when the review index explicitly names it as the required mapping
    # location; extension sections are permitted by their declaration.
    for item in scoring_items:
        section = section_by_id[item["section_id"]]
        if not section["allow_extensions"] and item["section_id"] != index["section_id"]:
            raise TenderContractError(
                f"tender scoring item {item['id']} section is not an extension location "
                "or required score mapping"
            )


def review_index_findings(contract: dict, *, strict_pages: bool) -> list[str]:
    """Return deterministic semantic findings for the declared review index."""
    validate_tender_contract(contract)
    scoring = {item["id"]: item for item in contract["scoring_items"]}
    expected = [item["id"] for item in sorted(contract["scoring_items"], key=lambda item: item["order"])]
    findings: list[str] = []
    seen: set[str] = set()
    positions: list[str] = []
    for row in contract["review_index"]["rows"]:
        item_id = row["item_id"]
        if item_id in seen:
            findings.append(f"review index duplicate item {item_id}")
        seen.add(item_id)
        if item_id not in scoring:
            findings.append(f"review index unknown item {item_id}")
            continue
        positions.append(item_id)
        item = scoring[item_id]
        accepted = {item["label"], item["source_label"], *item["aliases"]}
        accepted_normalized = {normalize_label(label) for label in accepted}
        if normalize_label(row["label"]) not in accepted_normalized:
            findings.append(
                f"review index label mismatch for {item_id}: expected {item['source_label']!r}"
            )
        if strict_pages and row["page"] is None:
            findings.append(f"review index page is not filled for {item_id}")
    for item_id in expected:
        if item_id not in seen:
            findings.append(f"review index missing item {item_id}")
    known_positions = [item_id for item_id in positions if item_id in scoring]
    if known_positions != [item_id for item_id in expected if item_id in seen]:
        findings.append("review index rows are out of scoring order")
    return findings


def build_writer_checklist(contract: dict) -> list[dict]:
    """Build the source-ordered checklist used while drafting a response."""
    validate_tender_contract(contract)
    sections = {section["id"]: section for section in contract["sections"]}
    rows = {row["item_id"]: row for row in contract["review_index"]["rows"]}
    result = []
    for item in sorted(contract["scoring_items"], key=lambda item: item["order"]):
        row = rows.get(item["id"])
        result.append(
            {
                "item_id": item["id"],
                "source_label": item["source_label"],
                "response_location": sections[item["section_id"]]["title"],
                "evidence_ids": list(item["evidence_ids"]),
                "review_index_page": row["page"] if row is not None else None,
                "status": "ready" if row is not None and row["page"] is not None else "pending",
            }
        )
    return result


def reverse_evidence_map(contract: dict) -> dict[str, list[str]]:
    """Return evidence/material IDs mapped back to scoring items in source order."""
    validate_tender_contract(contract)
    result: dict[str, list[str]] = {}
    for item in sorted(contract["scoring_items"], key=lambda item: item["order"]):
        for evidence_id in item["evidence_ids"]:
            result.setdefault(evidence_id, []).append(item["id"])
    return result


__all__ = [
    "TenderContractError",
    "build_writer_checklist",
    "normalize_label",
    "reverse_evidence_map",
    "review_index_findings",
    "validate_tender_contract",
]
