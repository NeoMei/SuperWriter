# Superwriter Round-2 Fix Report

**Baseline:** `30c4b7e1a17378240e8489ab08831983056eed95`

**Scope:** All seven findings in `audit-round2-superwriter.md`. No external/customer bid workspace was modified; only the repository's simulated acceptance fixture was updated.

## RED evidence

- Default managed-source installation failed reproducibly with `Unsafe source/target overlap` before implementation.
- A relative `WPSCOMPOSER_SKILL_SOURCE` installed but static verification rejected its absolute installed link.
- The previous acceptance verifier accepted a missing manifest, missing `流水线状态.md`, a materially changed `合并稿.md`, and fully overlapping Excalidraw nodes.
- The prose-only wait deny-list could be bypassed and was not a reliable execution contract.

## Fixes

1. `install.sh` snapshots all agents-host dependency sources into an independent `/tmp` transaction directory before any managed target mutation. All three host candidates are built from the snapshot. WPS/source and other genuinely destructive overlaps remain rejected.
2. Added a project-owned, machine-readable `验收清单.json` and reusable `references/验收清单模板.json`. Generic acceptance reads only manifest-declared point IDs, terms, chapters, figures/captions, output paths, and PDF constraints; demo constants were removed from the verifier.
3. Acceptance now requires stage 0–9 evidence, stage 9 completion, gates 0/2/3/5/6/7/8, exactly three human interventions, equal score/matrix counts, unique checked mappings, 100% coverage, outline/chapter mapping, all declared chapters, and no unresolved placeholders.
4. The generation manifest stores the exact merged-draft SHA-256. Verification also normalizes every substantive merged-draft line and requires coverage in both extracted DOCX and PDF text, so updating only the digest cannot bless stale exports.
5. Each figure records source/render SHA-256, expected node labels, geometry, directed topology, edge labels, caption, and optional renderer command. Verification rejects overlap or topology/label drift before checking the source digest, verifies the PNG digest/decodability, optionally renders when the declared renderer is callable, and still compares DOCX-embedded pixels to the accepted PNG.
6. Added `references/阶段契约.json` as the sole per-stage execution contract. Its exact metadata permits waits only at stages 2/5/8. `SKILL.md` states that prose mentioning a user response does not pause a machine stage; prose scanning is now warning-only.
7. `scripts/verify.sh` canonicalizes HOME and every source override before availability/link comparisons, matching installer behavior for relative WPS paths.

## GREEN verification

- `bash -n install.sh scripts/verify.sh tests/test_install.sh tests/test_verify_artifacts.sh`
- `python3 -m py_compile scripts/verify_acceptance.py`
- `bash tests/test_install.sh`
  - Includes default managed-source installation + replay.
  - Includes relative-WPS install → static verify.
  - All path, route, staging, commit, and rollback cases passed.
- `bash tests/test_verify_artifacts.sh`
  - All static-manifest, dependency/runtime, backup, structured-stage, acceptance-manifest, pipeline, matrix, outline, placeholder, stale-export, Excalidraw/PNG/DOCX/PDF, and missing-tool mutations passed.
  - A PDF whose declared page count changed from three to two was accepted under the project-declared positive page range, proving the generic verifier no longer hard-codes the demo page count.
- `python3 -B scripts/verify_acceptance.py '验收/模拟客户A/模拟标段1'`
  - Explicit simulated acceptance passed.
- `git diff --check`

## Result

All seven round-2 findings are closed by executable contracts and regression coverage.

## Follow-up independent-review fixes

The independent review at `round2-superwriter-fix-review.md` found two Important trust-binding gaps and one Minor schema gap. They were reproduced before implementation: deletion plus digest refresh, merged-path repointing, source geometry plus digest refresh, source+SVG changes with an old PNG, duplicate keys, unknown keys, and duplicate chapter declarations all false-greened.

- Acceptance now fixes `outputs.merged` and stage-7 evidence to the project-root `合并稿.md`, confines DOCX/PDF directly to `导出/`, and fixes stage-9 evidence to the declared DOCX. Structured fingerprints are derived dynamically from the canonical draft (headings, paragraphs, table rows, and key tokens). Both extracted outputs must contain every source fingerprint, and every substantive export body line must occur in the source; only explicit cover/TOC wrappers are exempt.
- Every accepted figure now requires a same-name structured SVG render source. Excalidraw and SVG node IDs, labels, exact geometry, directed topology, and edge labels are compared; SVG rendering through macOS `sips` is mandatory and fail-closed; normalized SVG raster pixels must match the accepted PNG before PNG↔DOCX comparison.
- JSON parsing rejects duplicate keys. The acceptance manifest is a closed schema at every object level, digests must be lowercase SHA-256, and point/term/chapter/evidence/figure path uniqueness is enforced. The stage contract uses the same duplicate-key rejection and its existing exact-value comparison rejects unknown fields.

The repository demo had a stale, text-only SVG that did not correspond to its Excalidraw/PNG. Correcting that original source-render inconsistency required regenerating only the diagram chain: the SVG was replaced by the structured canonical render, the PNG was produced from it with `sips`, and only `word/media/image1.png` was replaced in the demo DOCX. The PDF was then converted from that DOCX through the real WPS conversion backend. DOCX package validity, `WPS Office` application metadata, DOCX/PDF extracted正文, WPS PDF Creator, three A4 pages, SVG→PNG pixels, and PNG→DOCX pixels were revalidated; no bid prose or layout semantics were rewritten by a test bypass.
