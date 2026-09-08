# Independent rereview of core corrections

Scoped approval: model/workflow changes and new boundary/outline regressions, after second correction of repeated retention. Read-only reviewer; no source edits.

First independent pass reproduced a remaining P1: reorder v2, retain chapters, then unchanged-order v3 retention resurrected old aggregates without rereview. Original repro and failure are /tmp/superwriter-core-repeat-outline-probe.py and /tmp/superwriter-core-repeat-outline-red.log.

Correction now reconstructs the outline composition at this exact aggregate's immutable registration. Independent unchanged standalone probe now leaves figure-set/manuscript/layout stale at v3, next_action is revise figure-set, and delivery readiness rejects. Evidence /tmp/superwriter-core-repeat-outline-independent-fixed.log.

64 selected core/model/workflow/retention tests pass in /tmp/superwriter-core-independent-final.log. Reviewed added/removed/reordered and repeated outline coverage, missing mandatory aggregate chapter dependencies, malformed event enums and no-change retention. Additional real commit/load probes proved complete repair after reorder, removing chapter one, or removing chapter two can proceed through fresh figure-set/manuscript/layout reviews to export; no new deadend was observed.

No remaining concrete important finding in this scoped patch. This approval does not cover PDF acceptance fixes or actual-browser/WPS behavior.
