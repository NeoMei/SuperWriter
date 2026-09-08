# Independent final PDF acceptance rereview

Scoped approval of the frozen fixes to the two independently reproduced failures. No source edits made by this reviewer.

1. Opaque white image overlay: unchanged standalone probe now exits 1 with `PDF expected diagram is missing or its pixels differ from the approved figure`. New code requires both the registered image pixels and the actual rendered page region to match, with the image fully inside the page; white overlay cannot pass merely because the original image resource/paint operation survives. The display extent tolerance is one point, while embedded aspect and pixel tolerances remain unchanged.
2. Additional terminal body numeral: unchanged five-page probe inserting `5` at (84,740) now rejects substantive body text. Native furniture removal returns an explicit flag; integration passes no legacy terminal-page-number allowance after successful geometry-based cleanup. Unsupported/non-longform layouts return false, retaining previous fallback behavior.

Independent 14-test suite passes, including real WPS positive image fixture, original five-page WPS text, missing/altered/unpainted/covered illustrations, bad footer and TOC references, extra and removed body text, and explicit missing PyMuPDF dependency behavior.

Both actual legacy v1 and collaboration v2 fixture deliveries also passed the full verifier independently using disposable copies.

Evidence: /tmp/superwriter-pdf-final-review-probes.log and /tmp/superwriter-pdf-final-review.log. No remaining concrete important finding in this bounded patch. These tests do not establish user signoff or a new release/deployment.
