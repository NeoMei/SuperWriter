# Superwriter / WPSComposer final comprehensive audit

Date: 2026-08-18

## Final state

- Superwriter branch: `codex/superwriter-bug-audit` at `f1c725795df23fa6d8b00c68b01e0d8f2db0ad64` before this report commit.
- WPSComposer branch: `codex/wpscomposer-bug-audit` at `1f89f463451d44dbe9edf5ceb9614797964f30b0`.
- Three broad audit rounds were completed. Every Critical, Important, and favorable-risk Minor finding was reproduced, fixed with a failing regression first, and independently re-reviewed.
- Final fix reviews report `Critical 0 / Important 0 / Minor 0` for Superwriter, WPS core, WPS runtime, and the spawn-safe full-suite repair.

## Main repair areas

### Superwriter

- Transactional, path-safe, replayable installation across Agents, Claude, and Codex hosts, including rollback failure recovery and exact route-marker handling.
- Static verification separated from explicit project acceptance; no implicit bundled-demo acceptance.
- Strict project acceptance manifest/schema, 0→9 stage evidence, gates 2/5/8 evidence, matrix/outline/chapter checks, placeholder rejection, and current-source/export synchronization.
- Full source→SVG→rendered PNG→DOCX relationship validation with visible edge geometry, direction, topology, dimensions, and normalized pixels.
- Ordered, counted, full-Unicode DOCX/PDF content comparison, including combining marks, symbols, emoji sequences, and short text.
- Exact integer typing and strict duplicate/unknown-key rejection in JSON contracts.

### WPSComposer

- Atomic generation, editing, PDF transformation, grouped publication, rollback, and recovery-artifact preservation.
- Correct Writer/Slide/Sheet rendering, Markdown image semantics, slide element order, table pagination, stable nested IDs, and counted OOXML semantic validation.
- Safe COM ownership and cleanup: balanced COM apartments, no `Quit()` or global property mutation on shared user WPS instances.
- Safe macOS process ownership, direct-child identity handshake, no elapsed-age PID inference, exhaustive cleanup, stable registration recovery, and merge-safe external registration preservation.
- One end-to-end deadline across locks, services, activation, bridge commands, staging, validation, and publication.
- One-time fragment bootstrap capability bound to component/client, no public session nonce, short lease, and authenticated refresh behavior.
- Spawn-safe artifact validator protocol using serializable specifications, with complete pipe/child cleanup on constructor/start/timeout failures.

## Final verification evidence

- Superwriter:
  - `bash tests/test_install.sh` — PASS.
  - `bash tests/test_verify_artifacts.sh` — PASS, including all mutation cases.
  - `python3 -B scripts/verify_acceptance.py 验收/模拟客户A/模拟标段1` — PASS.
  - DOCX ZIP integrity, WPS application metadata, PDF WPS creator metadata, syntax, Python compilation, and `git diff --check` — PASS.
- WPSComposer:
  - With the repository's pinned `wpsjs` fixtures linked into the audit worktree and optional PDF test dependencies installed in the existing local virtualenv: `828 passed in 54.27s`, zero failures and zero skips.
  - `python -m compileall`, `git diff --check`, and tracked worktree status — PASS/clean.
  - The temporary `node_modules` link was removed after verification; the main worktree's pre-existing untracked `uv.lock` was not modified.

## Non-code external dependency

The repository includes and passes the simulated small-bid acceptance. A real-customer bid cannot be truthfully replayed without the customer's tender files, source materials, and actual confirmations at gates 2, 5, and 8. This is an external input requirement, not a remaining code bug.

## Verdict

No reproduced Critical, Important, or worthwhile Minor code defect remains open after the final review and full-suite run. The branches are ready for local fast-forward integration and installation.

