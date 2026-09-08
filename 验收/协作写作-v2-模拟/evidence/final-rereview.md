# Final fix scoped rereview

## Verdict

**Specification and code quality: Changes required.** Three original findings are addressed. The collection-only fix removes the original blocker but introduces one Important regression at the explicitly retained-outline boundary.

## Per original finding

1. **Collection-only approval: NOT fully addressed.** Creating, submitting and explicitly approving a set of registered draft figures now works without fabricated individual approvals. Workflow and final acceptance share exact current-registration coverage. However, the new draft-member path is incompatible with selective retained-chapter restoration, as detailed below.
2. **Legacy continuation references: ADDRESSED.** `SKILL.md` now points to the installed `继续旧项目.md` wrapper. Its root-relative mapping resolves every frozen skill reference, redirects the three changed v1 contracts and explicitly preserves legacy stages/gates. Frozen provenance files remain untouched. The installed-copy regression checks actual mapped files and version/gate contents across all three hosts.
3. **Delivery example: ADDRESSED.** Both paths use `导出/`, and the text now correctly separates validation-only PASS from the agent's completion event.
4. **Readable state: ADDRESSED.** Generated Markdown includes material readiness/resolution/affected objects, typed current invalidations and workflow-derived next action/blockers, while explicitly keeping JSON authoritative.

## Important regression introduced by finding 1 fix

**Location in fix:** `scripts/collaboration/workflow.py:100–121`; integration requiring correction: `scripts/collaboration/model.py:625–660` (`_restore_discharged_descendants`).

Collection coverage intentionally leaves a member `draft` without an individual approval. When an outline changes and the user explicitly retains all unchanged chapters, `_retain_outline_chapters` restores those chapters and removes their invalidation causes. `_restore_discharged_descendants` refuses to restore the collection-approved figure because `_effective_approval` only recognizes an individual approval record. The figure's old dependency cause remains, but its retained chapter no longer has the upstream cause required by `_dependency_invalidation_has_provenance`. Final `validate_state` therefore rejects the valid outline approval with **`dependency invalidation provenance is invalid`**. The durable commit rolls back; the user cannot complete the promised retention action.

**Observed reproduction, using only in-memory public reducer events:**

1. Register and approve approach, outline v1 with `chapter_order=[c1,c2]`, and c1/c2.
2. Register `fig1` draft depending on c1 v1; register and approve `figure-set` with current dependencies on c1/c2/fig1. `next_action` correctly returns draft manuscript.
3. Register outline v2 with unchanged chapter order and submit it.
4. Approve outline v2 with `retain_chapters` entries for both current unchanged chapters (version 1, matching SHA-256, previous outline version 1).
5. `apply_event` rejects with `dependency invalidation provenance is invalid`.

No forged state was needed for the confirming reproduction, and no files/state were mutated. This is within the new collection-only path and the existing binding ruling for selective retention, not a newly expanded review scope.

**Required correction:** make restoration/invalidation handle figures covered by an explicit current collection approval while preserving their individual draft/pending status and exact registration identity. A valid retention decision must save successfully; unchanged covered figures/collections should retain effective coverage when all relevant causes discharge. Do not invent individual approval events or weaken unrelated content-drift/change-request rejection. Add the public store/reducer sequence above as a focused regression, including a still-affected member so unrelated causes continue to block coverage.

## Evidence and scope

- Reviewed only the nine-file `final-fix-review.patch`, its fix report/freeze and the four original findings plus new breakage directly caused by that diff.
- All nine live file digests match `final-fix-source-freeze.json`; patch SHA-256 is `1c6954f63b0aa8b8b34b6f606fe71a33f217038141fd89b0a58e951c8f258b8b`.
- The log records **164 Python tests passing**. Read the targeted behavior tests, installed-legacy smoke report and unchanged native acceptance result; did not rerun broad suites. Parent owns final install/artifact/isolated checks.
- Only this report was written. No production/index/branch/native or customer-state edits; no subagents; no claim of real-user acceptance or deployment.

## Runnable in-memory reproduction

Run from the worktree root; this performs no file writes:

```python
from scripts.collaboration.model import initial_state, apply_event
from scripts.collaboration.workflow import next_action

state = initial_state("synthetic-retention-probe")
sequence = 0

def send(kind, obj, payload=None, channel="agent"):
    global state, sequence
    sequence += 1
    state = apply_event(state, {
        "id": str(sequence), "kind": kind, "object_id": obj["id"],
        "version": obj["version"], "sha256": obj["sha256"],
        "channel": channel,
        "evidence": {"reference": "synthetic-test", "text": "Synthetic probe"},
        "payload": payload or {},
    })

def put(object_id, kind, dependencies, metadata=None, version=1):
    obj = {
        "id": object_id, "kind": kind, "path": object_id + ".md",
        "version": version, "sha256": str(version) * 64,
        "dependencies": dependencies, "metadata": metadata or {},
        "status": "draft",
    }
    send("put_object", obj, {"object": obj})
    return obj

def approve(obj):
    send("submit_review", obj)
    send("approve", obj, channel="chat")

approve(put("approach", "approach", {}))
approve(put("outline", "outline", {"approach": 1},
            {"chapter_order": ["c1", "c2"]}))
for chapter in ("c1", "c2"):
    approve(put(chapter, "chapter", {"approach": 1, "outline": 1},
                {"required_material_ids": []}))
put("fig1", "figure", {"c1": 1})
approve(put("figure-set", "figure_set", {"c1": 1, "c2": 1, "fig1": 1},
            {"figure_ids": ["fig1"], "mode": "generated"}))
print(next_action(state))  # draft manuscript: collection approval works
outline = put("outline", "outline", {"approach": 1},
              {"chapter_order": ["c1", "c2"]}, version=2)
send("submit_review", outline)
send("approve", outline, {
    "retain_chapters": [
        {"id": chapter, "version": 1, "sha256": "1" * 64,
         "previous_outline_version": 1}
        for chapter in ("c1", "c2")
    ]
}, channel="chat")  # raises CollaborationError: dependency invalidation provenance is invalid
```
