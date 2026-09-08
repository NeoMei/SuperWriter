# Final independent PDF rasterization rereview

Approved within the requested final rasterization scope. Read-only review; no source changes or Git mutations.

Reviewed validate_pdf_figures: approved JPEG is decoded through PyMuPDF before the same sips normalization used for the embedded PDF pixmap. Source-versus-embedded pixel validation remains mandatory and retains the original mean/large-error thresholds. The visibility comparison now rasterizes the already-validated embedded pixmap onto a blank reference page using identical page dimensions, image bounds and 2x matrix, then compares that reference crop with the actual page crop. This removes filter/decoder disagreement without allowing arbitrary embedded pixels. In-page bounds, embedded aspect and one-point display-extent checks remain enforced. Actual-page overlays are present only in the actual crop and therefore still fail.

Reviewed shell test changes: converted legitimate fixtures synchronize their PDF image with the transformed approved source and DOCX. The helper is bounded to the single image fixture and asserts exactly one replacement; it does not weaken verifier checks. PYTHONUSERBASE preserves the invoking interpreter's dependency search under fixture HOME isolation and installs nothing.

Fresh validation:
- Original exact opaque-overlay and extra-terminal-body-number probes both reject. /tmp/superwriter-pdf-raster-probes.log
- All 14 native-PDF/figure regression tests pass. /tmp/superwriter-pdf-raster-tests.log
- Independent JPEG-specific probe: converted approved JPEG in the legacy WPS PDF passes; the same JPEG hidden beneath white overlay fails; replacing all actual image resources with white pixels fails. /tmp/superwriter-pdf-raster-jpeg-probe.log

A first disposable JPEG corruption attempt replaced a duplicate unused xref reported by get_image_info rather than the painted resource; it was corrected to mutate every fixture image resource before drawing conclusions. The final rejection probe changes actual visible pixels.

No remaining concrete important finding was observed in this bounded final change. Full artifact shell suite status remains owned by the root run at /tmp/superwriter-audit-artifacts-final-green.log; this report does not claim that run's completion.
