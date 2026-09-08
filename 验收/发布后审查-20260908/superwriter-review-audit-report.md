# SuperWriter review UI/backend audit and repairs

Baseline: worktree superwriter-audit-020, HEAD 67d1d6a. Current changes remain uncommitted for root review. Scope: review_server.py, review_assets/*, test_review_server.py, new test_review_ui.py and review_ui_harness.js. All customer data used here were disposable synthetic fixtures. No CUA/browser session touched.

## Confirmed defects and resulting behavior

1. Single-threaded HTTPServer blocked every request behind an idle TCP connection. Reproduction: open an idle socket, issue an authenticated GET on another connection; it times out until idle socket closes. ThreadingHTTPServer now serves the second request. Concurrent six-way approval test proves exactly one commit and five conflicts under store locking.
2. JSON event id=[] and kind={} caused unhandled TypeError and RemoteDisconnected before store validation. Boundary now validates string id/kind/channel and returns JSON 400; non-ASCII token comparison now returns 403 instead of crashing.
3. Single-figure review returned image bytes correctly but always used undeclared caption/placement, even when a unique containing current figure-set declared both. It now resolves that one set when its member dependency binds the current figure version; absent, ambiguous, stale or mismatched sets do not supply guessed declarations.
4. Image snapshots were decoded as text, filling current/previous comparison panes with PNG replacement characters or SVG source. Snapshot API now identifies image previews; frontend renders versioned previews. Image URLs bind version and SHA-256 and resolve only that object's registered current/historical identity, avoiding newer bytes under an older label.
5. Successful POST followed by failed GET displayed '未保存' despite persisted approval. UI now preserves an '已记录' message, reports refresh failure separately, and disables further actions until refresh. An uncertain POST response reports that the result needs checking rather than asserting no save; this also covers a derived view-write error after durable state commit.
6. Actions remained enabled while an earlier action was saving. A busy guard now blocks concurrent clicks.
7. An old asynchronous image render could append obsolete figures after a newer render. Render generations discard obsolete results and revoke obsolete blob URLs.
8. HTTP failure loading an image was silently omitted. It now displays a local visible image-preview failure message.

## Validation

- Original review suite: 14 tests passed; none covered the defects above.
- Expanded suite: 20 tests = 19 HTTP/Python cases plus one Node VM runner with five independently asserted frontend network/race cases.
- Added coverage: nofigure decision and 1,000-line manuscript content preserved in full; invalid image identity query cannot serve bytes; registered previous image bytes remain accessible after revision; directfigure ambiguous/mismatched declarations remain honest; current/previous image snapshots are not returned as text.
- JS syntax: node --check scripts/review_assets/review.js.
- Node harness is synthetic DOM/network behavior testing, not browser visual acceptance. Root is responsible for actual browser validation, including valid PNG decoding, layout and interactive approval flow.

## Evidence files

- /tmp/superwriter-review-red.log — failing HTTP regressions on baseline.
- /tmp/superwriter-ui-red.log — initial saved/refresh failure regression.
- /tmp/superwriter-ui-red-all.log — all four original async regressions fail against immutable HEAD JavaScript copied to /tmp/superwriter-review-original.js.
- /tmp/superwriter-ui-red-uncertain.log — fifth test initially fails on lost response.
- /tmp/superwriter-review-green.log — final expanded suite result.

## Review boundaries

No implementation claims were made about WPS output, release/installation, actual-user approval, or full-browser accessibility. Plain Markdown content rendering intentionally remains textContent/pre as specified; no rich Markdown renderer was added. Figure caption/placement fallback remains explicitly undeclared when there is no unique eligible source. Image decoding failures in a browser (corrupt-but-HTTP-200 bytes) still rely on the browser's broken-image presentation, while HTTP/network failures now have explicit text.
