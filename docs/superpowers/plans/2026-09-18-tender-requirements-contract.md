# Tender Requirements Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make protocol v2 tender projects machine-check the declared response structure, scoring-item order, review-index completeness/page placeholders, and two-way evidence mapping without changing the fixed tender structure or making Word the canonical source.

**Architecture:** Add a small standard-library contract module that validates a source-bound tender declaration and derives the writer checklist/reverse evidence map. Make the declaration an optional `checks.tender_contract` extension so existing v2 projects remain compatible, but validate it whenever a project opts in. Keep actual source interpretation and legacy `.doc` conversion explicit: the contract records the source locator and source labels; it never silently invents sections or aliases.

**Tech Stack:** Python 3.10+, `unittest`, JSON-shaped metadata, existing protocol v2 collaboration checks and acceptance verifier.

**Spec:** `/Users/neomei/Downloads/标书制作复盘与superwriter优化清单_2026-09-17(1).md`, especially the P0/P1 requirements at lines 92-116, interpreted against `/Users/neomei/Downloads/AI咨询合作伙伴招募项目招募文件（定稿）.doc`.

## Global Constraints

- Preserve fixed tender section order and headings; scoring order may only organize an explicitly allowed extension section.
- Preserve the current Markdown manuscript → WPSComposer DOCX/PDF delivery source of truth; do not implement Word-first round-tripping in this change.
- Preserve legacy-v1 and v2 projects without `checks.tender_contract`; the extension is enforced only when declared.
- Do not claim raw `.doc` parsing; the contract must retain a source locator and exact source labels and report conversion/verification gaps explicitly.
- Use explicit label aliases for known source typos such as `报价响应逮度` ↔ `报价响应速度`; normalization must not silently rewrite source text.

---

### Task 1: Add the tender contract and derived checklists

**Files:**
- Create: `scripts/tender_contract.py`
- Create: `tests/test_tender_contract.py`

**Interfaces:**
- `validate_tender_contract(value: object) -> None` raises `TenderContractError` for malformed declarations.
- `review_index_findings(contract: dict, *, strict_pages: bool) -> list[str]` reports missing, duplicate, unknown, mismatched-label, and unfilled/invalid page rows in scoring order.
- `build_writer_checklist(contract: dict) -> list[dict]` returns one row per declared scoring item in source order with response location, evidence IDs, and review-index page.
- `reverse_evidence_map(contract: dict) -> dict[str, list[str]]` maps every evidence/material ID back to scoring-item IDs.

- [x] **Step 1: Write failing tests** for the exact contract shape, fixed section order, score-item order, missing review-index rows, duplicate rows, explicit typo aliases, strict page validation, checklist order, and reverse evidence mapping.
- [x] **Step 2: Run `PYTHONPATH=. python3 -m unittest tests.test_tender_contract -v`** and confirm failures are due to the missing module/behavior.
- [x] **Step 3: Implement the minimal standard-library module** with exact-key validation, source-label preservation, explicit aliases, and deterministic derived outputs.
- [x] **Step 4: Re-run the focused tests** and confirm all pass.
- [x] **Step 5: Commit** with `feat: add tender requirements contract`.

### Task 2: Bind the contract to protocol v2 checks and acceptance

**Files:**
- Modify: `scripts/collaboration/checks.py`
- Modify: `scripts/verify_acceptance.py`
- Test: `tests/test_outline_structure_regressions.py`
- Test: `tests/test_verify_acceptance.py`

**Interfaces:**
- `checks.tender_contract` is optional in `validate_checks`; when present it delegates syntax validation to `tender_contract.validate_tender_contract` and raises `CollaborationError` with a stable prefix.
- v2 tender acceptance reads the current approved outline checks; when `tender_contract` is present it rejects review-index findings with `strict_pages=True` before accepting DOCX/PDF delivery.
- Existing projects without `tender_contract`, professional projects, and legacy-v1 continue through their existing paths.

- [x] **Step 1: Add failing schema tests** for valid/invalid tender contracts and compatibility without the optional field.
- [x] **Step 2: Run the focused schema tests** and confirm the new cases fail before integration.
- [x] **Step 3: Add failing acceptance tests** for a missing review-index item, duplicate item, unfilled page, and a fully populated valid contract bound to the approved outline.
- [x] **Step 4: Run the focused acceptance tests** and confirm they fail for the intended contract findings.
- [x] **Step 5: Implement the optional schema binding and acceptance gate** without changing existing point/matrix checks or template/layout behavior.
- [x] **Step 6: Re-run both focused suites** and confirm all pass.
- [x] **Step 7: Commit** with `fix: enforce tender review index contract`.

### Task 3: Document the workflow and provide contract/checklist templates

**Files:**
- Modify: `SKILL.md`
- Modify: `references/结构化核验.md`
- Modify: `references/结构化核验模板.json`
- Modify: `references/招标响应结构模板.md`
- Modify: `references/应答矩阵模板.md`
- Modify: `references/协作交付验收.md`
- Test: `tests/test_workflow_contract.py`

**Interfaces:**
- Guidance states that fixed sections are source-bound, scoring order is used only within permitted extension locations, and `tender_contract` records the exact source labels/aliases and review-index rows.
- The JSON example contains a complete opt-in `tender_contract` skeleton with a deliberate placeholder page state; no automatic approval is implied.
- The workflow exposes the derived writer checklist and reverse evidence map as review aids, while final delivery requires strict filled pages.

- [x] **Step 1: Add failing guidance tests** for the contract name, fixed-section rule, explicit alias rule, writer checklist, and strict delivery page requirement.
- [x] **Step 2: Run the guidance tests** and confirm they fail before documentation changes.
- [x] **Step 3: Update the workflow and JSON examples** with the exact contract shape and the no-Word-first boundary.
- [x] **Step 4: Re-run guidance tests and the complete Python regression suite.**
- [x] **Step 5: Run `bash tests/test_install.sh`, `bash tests/test_verify_artifacts.sh`, `python3 scripts/verify.py`, and `git diff --check`.**
- [x] **Step 6: Commit** with `docs: document tender requirements and index checks`.

## Review Checklist

- [x] A fixed section such as `9、资格审查资料` or `10、类似业绩` cannot be silently moved under `11、申请人认为需要提供的其他文件`.
- [x] All declared scoring items appear exactly once in the review index; known source typos require explicit aliases.
- [x] Writer checklist rows and reverse evidence mappings are deterministic and preserve source order.
- [x] Strict delivery rejects missing/invalid final page numbers but permits draft placeholders before delivery.
- [x] Existing v2 projects without the extension, professional documents, and legacy-v1 remain compatible.
- [x] No Word-first round-trip or raw `.doc` parser is claimed by the implementation.

## Verification record

- `PYTHONPATH=.:tests python3 -m unittest discover -s tests -p 'test_*.py'`: 345 passed, 2 skipped.
- `bash tests/test_install.sh`: 34 passed, 2 skipped.
- `bash tests/test_verify_artifacts.sh`: 13 passed.
- `WPSCOMPOSER_SKILL_SOURCE=/Users/neomei/项目/codexprojects/WpsComposer/skills/WPSComposer python3 scripts/verify.py --acceptance-dir 验收/模拟客户A/模拟标段1`: passed.
