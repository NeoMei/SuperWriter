# Whole-branch independent review

## Verdict

**Specification: Changes required. Code quality: Changes required.** No Critical finding. Two Important and two Minor findings remain in the integrated branch relative to `45a0bcf`.

## Important

### 1. Collection-only figure approval cannot reach the review page

**Location:** `scripts/collaboration/workflow.py:342–344`; corresponding downstream restrictions at `workflow.py:96–99` and `scripts/verify_acceptance.py:1085–1089`.

Confirmed design §6 explicitly permits either individual figure review or an explicit approval of the whole collection. The published skill tells the agent to register figures and present the figure-set review. However, `_mandatory_dependency_blockers` requires every figure to be individually `approved` even to create or submit that collection. The model has no collection-approval propagation/effective-coverage rule, and final acceptance independently repeats the individual-status requirement. Thus a user who wants to inspect and confirm all images together cannot use the documented HTML collection path without first providing redundant per-image approvals.

**Observed reproduction:** an in-memory reducer probe started from approved approach, outline and both chapters, registered a current draft `figure-01`, then attempted `put_object` for `figure-set` with exact current chapter/figure dependencies. It returned `cannot write figure-set: figure-01 must be approved` before collection review was possible. No filesystem/project state was changed by the probe. Existing tests and the native synthetic example approve each figure first, so they do not cover the allowed collection-only case.

**Correction:** permit a version-bound collection to be reviewed before individual approvals, and define durable exact-identity coverage from its explicit approval through workflow, invalidation and acceptance. Preserve the supported individual-review path and reject stale or changed collection members; do not fabricate per-figure user events.

### 2. The installed legacy continuation route resolves frozen contracts to v2 or missing paths

**Location:** `SKILL.md:15–16`; frozen `references/legacy-v1/SKILL.md:25`, `:114`, `:118`.

The legacy route only says to continue under `references/legacy-v1/`, but the byte-frozen legacy skill still declares `references/阶段契约.json` as its sole execution contract and names `references/验收清单模板.json` / `references/门禁清单.md`. From the installed skill root those paths now contain v2 contracts; resolving them relative to the frozen skill directory also fails because no `legacy-v1/references/` directory exists. The legacy directory contains only five flat files and no wrapper or explicit reference-resolution mapping. An unmigrated project therefore cannot follow the supplied skill references unambiguously without either consuming v2 rules/template or guessing remapped paths. This undermines the promised preservation of original execution semantics.

**Correction:** add an explicit installed legacy entry/wrapper mapping those three changed contracts to the flat frozen files while routing unchanged shared references to the skill root. Keep the provenance-protected frozen bytes unchanged and verify the actual installed continuation references, not just their existence/hash.

## Minor

### 3. The copyable delivery event example uses a directory rejected by acceptance

**Location:** `references/协作讨论规则.md:102–106`.

The example records `交付/方案.docx` and `交付/方案.pdf`, while `scripts/verify_acceptance.py:1220–1223` requires both outputs directly under `导出/`. Following this supplied example with real paths/hashes cannot complete the documented validation sequence. Change the sample to `导出/` and state that the agent records the event only after the validation-only verifier passes (the lead sentence currently attributes writing completion to the acceptance program).

### 4. The generated readable state entry omits material blockers and the next action

**Location:** `scripts/collaboration/store.py:170–214`.

Design §8 requires `流水线状态.md` to expose material gaps and the next step, but `_render_state_view` emits only stage/active ID, objects, preferences and approval history. It never renders `state["materials"]`, current invalidations, or the workflow-derived next action. For the demonstrated `agreed`-but-unverified critical material, a user reopening the promised readable entry cannot see what prevents the next chapter; this information exists only in JSON/`next`. Include concise material readiness/blockers and the derived next action in the generated view without making Markdown authoritative.

## Reviewed boundaries and evidence

- Reviewed the confirmed design, whole-branch immutable patch (production changes before synthetic state evidence), live final skill/references, reducer/store/workflow, review server/UI, migration, installer/verification closure and native acceptance integration; read progress rulings and the Task 7 final rereview.
- The source maintains explicit current-version approval records, strict event identity/idempotence, project-confined durable snapshots, disk/dependency invalidation, provenance-bound selective outline retention and a dedicated machine delivery record. I found no further concrete defect in the examined paths.
- Final Python log records **157 passing tests**. The reported install/artifact and scoped checks were not unnecessarily rerun. The native final evidence `验收/协作写作-v2-模拟/evidence/29-final-fix2-verification.json` records source/installed verifier SHA-256 `5a1902532bba6065e631114b55c9d3a18551be0c60660772fa2b129bbe2341f7`, unchanged revision 63, and PASS for both canonical and durable packages. The parent owns final artifact-suite completion and actual WPS/PDF visual inspection.
- Native artifacts and the final acceptance evidence are present in the durable simulated package; historical failures remain qualified. The report correctly distinguishes synthetic approvals from real-user acceptance and isolated installation from real-host installation. Nothing here claims a commit, merge, push, release or deployment.
- Read-only review: only this requested review report was written. No code, index, branch, customer state or native artifacts were edited; no subagents were spawned.
