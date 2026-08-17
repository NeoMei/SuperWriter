# Superwriter / WPSComposer Comprehensive Bug-Audit Plan

> Execution style: test-driven, root-cause-first, one implementation batch at a time, followed by an independent review. Every accepted finding must gain a regression test that fails before the fix and passes after it.

## Scope and worktrees

- Superwriter: `/Users/neomei/Library/Application Support/orca/codex-runtime-home/home/worktrees/f24d/superwriter`, branch `codex/superwriter-bug-audit`.
- WPSComposer: `/Users/neomei/项目/WpsComposer/.worktrees/wpscomposer-bug-audit`, branch `codex/wpscomposer-bug-audit`.
- Do not modify `/Users/neomei/项目/WpsComposer/uv.lock`; it is a pre-existing untracked user file in the main worktree.
- Preserve public behavior unless it is unsafe or contradicts the documented contract. Prefer explicit rejection over silent corruption or partial success.
- Do not terminate or reuse an unproven user WPS process. When ownership is uncertain, leak a task process with a diagnostic rather than risk user data.

## Task 1: Make Superwriter installation transactional and path-safe

**Files:** `install.sh`, `tests/test_install.sh`

1. Add failing tests for source/target identity (including symlink/same inode), empty or root-like `HOME`, relative WPS source, unmatched/duplicated route markers, and a failure at the second or third host.
2. Canonicalize all source paths before mutation and reject any source that is equal to, inside, or resolved through an install target.
3. Preflight every host, source, route file, marker pair, staging directory, and backup destination before changing any host.
4. Stage complete host trees and route files first; commit them only after all staging succeeds. On a commit failure, restore all already-committed hosts/routes from the transaction backup.
5. Replace route blocks only when exact start/end markers occur exactly once and in order; otherwise fail without modifying user content.
6. Re-run `bash tests/test_install.sh` and verify all failure cases leave sources and all hosts byte-for-byte unchanged.

## Task 2: Make Superwriter verification project-aware and tamper-resistant

**Files:** `scripts/verify.sh`, `tests/test_verify_artifacts.sh`, `tests/fixtures/fake_markitdown.sh`

1. Add failing tests proving the verifier rejects an implicit demo acceptance, all five reference/template mutations, stale/missing backup layouts, unlabelled artificial pauses, malformed PNGs, and unrelated DOCX media.
2. Split static installation/contract verification from acceptance verification. Require an explicit `--acceptance-dir DIR` for bid artifact checks; never silently substitute the repository demo.
3. Verify exact file manifests and hashes for all installed Superwriter files and required WPSComposer runtime assets; reject stale extras in the managed tree.
4. Parse exact gate metadata and reject unapproved user-wait instructions outside gates 2/5/8.
5. Discover backup directories by pattern and require them to remain outside discoverable skill roots regardless of date.
6. Validate PNG signature/chunks/dimensions and verify the DOCX relationship points to the expected embedded diagram with matching bytes.
7. Re-run artifact mutation tests, install tests, static verification, and explicit demo acceptance verification.

## Task 3: Preserve WPS generation and renderer content

**Files:** `skills/WPSComposer/scripts/orchestrator.py`, `md_parser.py`, `document_model.py`, `renderers/writer_renderer.py`, `renderers/slide_renderer.py`, `renderers/sheet_renderer.py`, `plugins/excalidraw.py`, `artifact_transport.py`, `pdf.py`, `_colors.py`, `slide.py`, `writer.py`, and focused tests under `tests/`.

1. Add regression tests for overwrite backend failure, first-H1 body loss, duplicate/empty H1 slides, >8-row tables, ordinary wikilink images, repeated table sheet names, Excalidraw sidecar overwrite, corrupt PDF, invisible semantic white, inline Markdown images, invalid plugin names, non-positive PDF pages, one-dimensional image sizing, and `bold=False` headings.
2. Preserve the old output until the new artifact is fully validated and atomically published; propagate `overwrite` to the backend.
3. Render first-H1 content without duplicating the document title; retain H1 slide body and paginate tables rather than truncate them.
4. Model normal images separately from Excalidraw blocks, generate unique deterministic sheet names, and never overwrite source-side plugin artifacts without explicit authorization.
5. Strengthen PDF and OOXML validation; fail closed when requested plugins or quality inspection cannot run.
6. Correct semantic colors, sizing, page bounds, and public boolean parameter behavior.
7. Run every focused RED/GREEN test and then the full WPSComposer suite.

## Task 4: Enforce atomic and format-safe document editing

**Files:** `skills/WPSComposer/scripts/document_api.py`, `macos_probe/inspection.py`, `macos_probe/models.py`, `macos/wps-jsapi-probe/addin/presentation.js`, composer abstractions, `tests/test_document_api.py`, and new `tests/macos_probe/test_inspection.py` coverage.

1. Add failing tests for composer-level `rejected` reports, attached-document multi-operation atomic edits, macOS mixed structural/set edits, partial patch failure, wrong reported output path, corrupt staged output, output collisions, cross-family formats, and macro/legacy presentation inputs.
2. Treat every rejected operation as failure. In atomic mode, do not save or publish any result unless all operations are accepted and successful.
3. If an attached live document cannot be reliably rolled back, reject atomic multi-operation mutation before the first mutation rather than claim atomicity.
4. For macOS, execute edits only on a staging copy; pass atomic/error semantics through the public API; reject unsupported structural operations before mutation.
5. Restrict macOS editing to verified `.pptx` input/output until format-preserving SaveAs implementations exist. Validate output family and collision/overwrite policy.
6. Require the bridge-reported path to equal the expected staged path, validate the OOXML package, and publish with destination-local atomic replacement.
7. Run focused tests and the full WPSComposer suite.

## Task 5: Make WPS process and COM ownership safe

**Files:** `skills/WPSComposer/scripts/_dispatch.py`, `_base.py`, composer close/open paths, `macos_probe/runtime.py`, `macos_probe/bridge.py`, vendor-server wrapper/assets, and focused runtime tests.

1. Add failing Windows-fake tests for `CoInitialize`/`CoUninitialize` balance, `DispatchEx` versus shared `Dispatch` ownership, open failure cleanup, and never quitting a shared user WPS application.
2. Add failing macOS tests for a user WPS launched during a run, a PID appearing during TERM grace, PID reuse, pre-existing young processes, vendor server launch side effects, stale recovery across different random runtime roots, concurrent registration edits, and stale bridge clients.
3. Track application/process ownership using verifiable identity (PID plus start time and executable). Signal only the fixed, initially proven owned set and revalidate before each signal. Remove elapsed-age ownership inference.
4. Replace or wrap vendor server startup so server mode does not call `open -a`; bind bridge commands to a session nonce/lease.
5. Store crash recovery under a stable, locked private directory, recover before port preflight, and use compare-and-swap/merge semantics so unrelated registration changes survive.
6. Balance COM apartments on every path, never `Quit()` a shared-dispatch application, and clean up all partial-open failures.
7. Run focused Windows-fake/macOS runtime tests and the full WPSComposer suite.

## Task 6: Enforce one end-to-end timeout budget

**Files:** `macos_probe/runtime.py`, `generation.py`, `conversion.py`, `inspection.py`, artifact validators, and focused fake-clock tests.

1. Add failing fake-clock tests covering lock wait, three server startups, activation retry, bridge registration/command, generation, and final validation under one small timeout.
2. Create the monotonic deadline at the public backend entry and pass only `remaining(deadline)` through every blocking stage and retry.
3. Do not reset the timeout for package/PDF validation. Keep cleanup grace short, bounded, and explicitly separate from the user deadline.
4. Run all macOS probe tests and the full suite.

## Task 7: Re-review until stable

1. Run a second independent review on both post-fix worktrees, emphasizing changed code, rollback/error paths, destructive operations, and contract compatibility.
2. Reproduce every Critical/Important finding and every worthwhile Minor finding; add failing tests and repair them using the same TDD loop.
3. Run a third independent review after the second repair wave. Stop only when reviewers report no remaining Critical/Important findings and no Minor finding with a favorable risk/benefit ratio.
4. Run fresh full verification from clean processes:
   - Superwriter install mutation suite, verifier mutation suite, static verification, and explicit acceptance-dir verification.
   - WPSComposer full pytest suite with the repository virtualenv interpreter.
   - Git diff checks and worktree status checks in both repositories.
5. Record accepted/deferred findings and exact evidence in `.superpowers/sdd/final-comprehensive-audit.md`. A deferred item must have an explicit technical reason; external real-bid inputs remain outside this code-fix scope.
