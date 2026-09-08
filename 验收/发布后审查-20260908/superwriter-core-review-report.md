# SuperWriter v0.2.0 core review and repairs

Scope: scripts/collaboration/model.py, store.py, workflow.py, migration.py, collaboration_state.py, related design/contracts/tests. Worktree baseline 67d1d6a. CodeGraph skipped because worktree has no index. No Git mutations. Only model.py, workflow.py, and two new regression files changed by this reviewer.

## Confirmed P1: outline structure changes incorrectly restored aggregate approvals

Original location: model.py _restore_discharged_descendants (old lines 676-703); workflow.py _delivery_blockers (old lines 137-154).

Reproduction uses real commit_event and load_state calls in a temporary project: approve two chapters, figure collection, and manuscript; register outline v2 with a third chapter; approve outline retaining both unchanged old chapters; write and approve chapter three. Original behavior: figure collection/manuscript approvals were restored; next_action returned export and require_delivery_ready passed although the manuscript bound only chapters one and two. Reordering both retained chapters also restored the old full manuscript despite changed composition. Removal was already blocked by the removed chapter's remaining invalidation and now has explicit regression coverage.

Fix: aggregate restoration requires matching chapter_order between current and previous registered outline versions. Otherwise aggregates remain stale; unaffected individual chapters/figures can remain accepted. Missing previous registration conservatively prevents aggregate restoration. Delivery readiness additionally checks figure-set/manuscript/layout mandatory current dependencies, catching obsolete missing-chapter bindings.

Regression coverage: additions, reordering, removal, unchanged order retaining all existing approvals, persisted recovery, and full repaired workflow through aggregate/manuscript/layout rereview to delivery readiness. No fixture mutation was necessary.

Standalone reproduction: /tmp/superwriter-core-outline-repro.py CHECKOUT
Original RED output: /tmp/superwriter-core-outline-red.log
Fixed reproduction output: /tmp/superwriter-core-outline-repro-fixed.log

## Confirmed P2: malformed event kind/channel caused uncontrolled TypeError

Location: model.py _validate_event lines 347-350 after repair.
Arrays/objects in event kind/channel reached set membership before string validation. UI reviewer independently observed this through HTTP. Added explicit string checks; errors are now CollaborationError. Regression commits all four malformed combinations through commit_event and checks byte-identical authoritative state after each rejection.

RED: /tmp/superwriter-core-envelope-red.log

## Validation

98 tests passed: test_model_boundary_regressions, test_outline_structure_regressions, test_collaboration_model, test_collaboration_workflow, test_collaboration_store, test_collaboration_migration, test_final_review_regressions.
Log: /tmp/superwriter-core-final-green.log

Bounded review covered approval identity/provenance, material blocking, creation/review guard differences, chapter ordering, figure collection effective approval, transitive invalidation, retention/recovery, file digest snapshots, lock/revision/idempotency handling, legacy source preview/backups/publication rollback, and CLI event confinement. No additional concrete important store/migration defect was reproduced. Acceptance/install/WPS/HTML are other reviewers' scopes; these test results do not establish actual WPS delivery acceptance.

## Follow-up independent review: repeated outline revision resurrection

The first aggregate guard compared only adjacent outline orders. Independent reviewer reproduced reorder v2 with retained chapters (aggregates stayed stale), followed by unchanged reordered v3 and retention (old aggregates were incorrectly restored). RED: /tmp/superwriter-repeat-retention-red.log.

Corrected implementation derives chapter_order at each aggregate's exact immutable put_object registration from durable processed_events. Restoration now compares that original composition with the current outline. Clearing a temporary dependency-change cause cannot erase that durable original binding. No schema migration is necessary. The regression exercises v2 reorder and repeated v3/v4 retention with load_state recovery, followed by real aggregate/manuscript/layout v2 rewrites and approvals, then v5 unchanged retention successfully preserving those newer approvals.

98 model/workflow/store/migration/retention tests pass: /tmp/superwriter-repeat-retention-green.log. Correction handed back to independent reviewer for another bounded review.
