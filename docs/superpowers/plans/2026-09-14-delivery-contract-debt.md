# Delivery contract debt implementation plan

> For agentic workers: use subagent-driven-development for bounded tasks, with independent review before completion.

Goal: fix persistent runtime entry, attachment lifecycle binding, explicit machine-readable structure/evidence checks, and professional-document acceptance.
Architecture: optional strict extensions preserve existing v2 state and frozen v1 semantics. New outline metadata `checks` binds attachments, headings and evidence to approval; record_delivery must match attachments. File drift invalidates downstream objects. Professional document type is bound to brief metadata and acceptance manifest, never inferred by a missing score file. Runtime setup is explicit and uses persistent per-user paths.
Tech stack: Python unittest, existing CLI/state reducer, Markdown references, platform-native Python.
Spec: user-approved four debt priorities in this task, 2026-09-14.

## Constraints
- No new approval stage; never invent existing approvals or migrate legacy state automatically.
- Checks validate declarations and bytes; no automatic certificate authenticity claims.
- No client material, system Python replacement, release or external publication in this implementation task.
- Preserve the released v0.2.6 install until source changes are verified; persistent runtime may be set up independently.

## Tasks
- [x] Runtime: add explicit setup/run CLI in scripts/runtime.py, persistent venv, actionable failures, portable tests; provision local environment and verify installed v0.2.6 with it.
- [x] Professional acceptance: optional brief.metadata.document_type and manifest document_type, tender by default; professional accepts generic requirement IDs and headings without score table while preserving required content/approval/output checks; reject profile mismatch and downgrade of tender state.
- [x] Attachment lifecycle: outline.metadata.checks.attachments list of {id,path,sha256}; optional record_delivery.payload.attachments must equal approved declarations. Validate portable unique paths, reject aliases/duplicates, verify bytes before record, and invalidate delivery on file deletion/replacement/symlink.
- [x] Structured checks: outline.metadata.checks contains heading_mode, headings [{chapter_id,level,title}], attachments, evidence [{material_id,path,sha256,chapter_id,source_locator,valid_until,as_of,applicability,support,material_sha256,scope,required_scope}]. Validate declared fields, dates, material ready state, association and file digests; compare ordered headings to approved chapter Markdown; allow explicit subsequence mode for permitted extra headings. Bind checks to review and recovery. Old outlines without checks remain valid, explicitly labelled unchecked.
- [x] Documentation and integration: explain schema, events, limits, profile and commands; add new runtime modules to installer manifests, extend compatibility tests.
- [x] Full verification and independent review: run targeted red-green cases, all Python suites, artifact acceptance, installed fixture tests; fix review findings then report actual boundaries.

For each implementation task first add rejection/acceptance tests and observe failure, implement minimal support, rerun affected suites. Integration tests must include attachment drift and byte restoration without auto-restoring approval, malformed fields, material mismatch/expired date, heading rename/reorder, tender/professional mismatch, and frozen legacy compatibility.

## Implementation evidence

- Added real state-event regression fixtures; checks must also appear in approved outline bytes. Registered brief/outline extensions cannot be deleted directly from state to bypass validation.
- Heading checks include ATX and Setext outside code fences/frontmatter; generic professional acceptance uses the same parser. Old unchecked tender numbering remains compatible.
- Evidence scope declares subject, product_version and period on both material and requirement sides; comparison checks declarations and snapshots only, not source authenticity.
- Persistent macOS Python 3.12.13 environment provisioned at `~/Library/Application Support/SuperWriter/runtime-v1`; selected runtime commands are first on child PATH. Existing installed v0.2.6 synthetic delivery passes using the source runtime entry with caller PATH restricted to system commands.
- Unmocked acceptance reuses immutable synthetic native WPS DOCX/PDF fixtures: professional profile plus exact heading checks and attachment passes before and after record_delivery; attachment replacement stales outline, manuscript and delivery. This is not a fresh WPS export.
- Independent review findings fixed: registered checks deletion bypass, uncounted Setext headings, and console dependencies resolving outside the selected runtime.
- Release/tag/push and installation of the new source package remain separate from this implementation. Installed skill mirrors remain v0.2.6. No native Windows execution was performed in this task.

## Final verification

- Persistent-runtime Python unittest discovery: 286 tests, OK, 2 native-Windows junction tests skipped on macOS.
- `bash tests/test_install.sh`: PASS; isolated installation, rollback and host-routing checks.
- `bash tests/test_verify_artifacts.sh`: PASS; malformed native artifact rejection and compatibility checks.
- `git diff --check`: PASS.
- Full-suite console-entry regression compares directory file identity to accommodate macOS `/var` and `/private/var` aliases while retaining exact caller PATH and actual venv console origin checks.
- Final bounded independent review: all three findings closed; reviewer reran 33 focused tests, all passed with no skips.
