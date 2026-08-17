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
