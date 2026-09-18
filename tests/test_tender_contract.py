import copy
import unittest

from scripts.tender_contract import (
    TenderContractError,
    build_writer_checklist,
    normalize_label,
    reverse_evidence_map,
    review_index_findings,
    validate_tender_contract,
)


def contract():
    return {
        "source_locator": "招募文件第三章第2条、第五章第2点",
        "structure_mode": "partial",
        "sections": [
            {
                "id": "S01",
                "title": "1、招募申请文件封面",
                "order": 1,
                "kind": "chapter",
                "parent": None,
                "allow_extensions": False,
            },
            {
                "id": "S11",
                "title": "11、申请人认为需要提供的其他文件",
                "order": 2,
                "kind": "chapter",
                "parent": None,
                "allow_extensions": True,
            },
        ],
        "scoring_items": [
            {
                "id": "P01",
                "label": "文件编写质量",
                "source_label": "文件编写质量",
                "order": 1,
                "section_id": "S11",
                "evidence_ids": ["material-format"],
                "aliases": [],
            },
            {
                "id": "P02",
                "label": "报价响应速度",
                "source_label": "报价响应逮度",
                "order": 2,
                "section_id": "S11",
                "evidence_ids": ["material-response", "material-format"],
                "aliases": ["报价响应速度"],
            },
        ],
        "review_index": {
            "section_id": "S01",
            "required_item_ids": ["P01", "P02"],
            "rows": [
                {"item_id": "P01", "label": "文件编写质量", "page": 8, "notes": ""},
                {"item_id": "P02", "label": "报价响应速度", "page": None, "notes": "待回填"},
            ],
        },
    }


class TenderContractTest(unittest.TestCase):
    def test_valid_contract_preserves_source_labels_and_order(self):
        value = contract()
        validate_tender_contract(value)
        self.assertEqual(value["scoring_items"][1]["source_label"], "报价响应逮度")
        self.assertEqual(normalize_label("报价响应 速度"), "报价响应速度")

    def test_unknown_contract_field_is_rejected(self):
        value = contract()
        value["unexpected"] = True
        with self.assertRaisesRegex(TenderContractError, "unknown field"):
            validate_tender_contract(value)

    def test_fixed_section_order_must_be_contiguous(self):
        value = contract()
        value["sections"][1]["order"] = 3
        with self.assertRaisesRegex(TenderContractError, "section order"):
            validate_tender_contract(value)

    def test_scoring_item_must_reference_an_existing_section(self):
        value = contract()
        value["scoring_items"][0]["section_id"] = "S99"
        with self.assertRaisesRegex(TenderContractError, "section"):
            validate_tender_contract(value)

    def test_fixed_section_requires_explicit_review_index_mapping(self):
        value = contract()
        value["scoring_items"][0]["section_id"] = "S01"
        value["review_index"]["section_id"] = "S11"
        with self.assertRaisesRegex(TenderContractError, "required score mapping"):
            validate_tender_contract(value)

        # A fixed section is a permitted score location when the review index
        # explicitly declares that section as the required score-mapping area.
        value["review_index"]["section_id"] = "S01"
        validate_tender_contract(value)

    def test_extension_section_is_a_permitted_scoring_location(self):
        value = contract()
        value["scoring_items"][0]["section_id"] = "S11"
        validate_tender_contract(value)

    def test_whitespace_only_ids_evidence_aliases_and_notes_are_rejected(self):
        cases = []

        value = contract()
        value["scoring_items"][0]["evidence_ids"] = ["   "]
        cases.append(value)

        value = contract()
        value["scoring_items"][0]["aliases"] = ["\t"]
        cases.append(value)

        value = contract()
        value["review_index"]["rows"][0]["notes"] = "\n"
        cases.append(value)

        for malformed in cases:
            with self.assertRaisesRegex(
                TenderContractError,
                "must contain strings|must be trimmed|trimmed nonempty",
            ):
                validate_tender_contract(malformed)

    def test_invalid_review_index_page_is_a_stable_contract_error_in_draft_and_strict(self):
        value = contract()
        value["review_index"]["rows"][0]["page"] = 0
        for strict_pages in (False, True):
            with self.assertRaisesRegex(
                TenderContractError,
                "review_index row page must be null or positive integer",
            ):
                review_index_findings(value, strict_pages=strict_pages)

    def test_review_index_reports_missing_duplicate_and_unknown_rows(self):
        value = contract()
        value["review_index"]["rows"] = [
            {"item_id": "P01", "label": "文件编写质量", "page": 8, "notes": ""},
            {"item_id": "P01", "label": "文件编写质量", "page": 9, "notes": "重复"},
            {"item_id": "P99", "label": "未知", "page": 10, "notes": ""},
        ]
        findings = review_index_findings(value, strict_pages=False)
        self.assertTrue(any("duplicate" in item for item in findings))
        self.assertTrue(any("unknown" in item for item in findings))
        self.assertTrue(any("missing" in item and "P02" in item for item in findings))

    def test_explicit_alias_accepts_source_typo_without_rewriting_it(self):
        value = contract()
        findings = review_index_findings(value, strict_pages=False)
        self.assertEqual(findings, [])
        self.assertEqual(value["scoring_items"][1]["source_label"], "报价响应逮度")

    def test_strict_pages_rejects_placeholder_but_draft_mode_allows_it(self):
        value = contract()
        self.assertEqual(review_index_findings(value, strict_pages=False), [])
        findings = review_index_findings(value, strict_pages=True)
        self.assertTrue(any("page" in item and "P02" in item for item in findings))
        value["review_index"]["rows"][1]["page"] = 12
        self.assertEqual(review_index_findings(value, strict_pages=True), [])

    def test_writer_checklist_and_reverse_evidence_map_are_deterministic(self):
        value = contract()
        checklist = build_writer_checklist(value)
        self.assertEqual([row["item_id"] for row in checklist], ["P01", "P02"])
        self.assertEqual(checklist[1]["response_location"], "11、申请人认为需要提供的其他文件")
        self.assertIsNone(checklist[1]["review_index_page"])
        self.assertEqual(
            reverse_evidence_map(value),
            {"material-format": ["P01", "P02"], "material-response": ["P02"]},
        )

    def test_derived_helpers_do_not_mutate_contract(self):
        value = contract()
        before = copy.deepcopy(value)
        build_writer_checklist(value)
        reverse_evidence_map(value)
        review_index_findings(value, strict_pages=False)
        self.assertEqual(value, before)


if __name__ == "__main__":
    unittest.main()
