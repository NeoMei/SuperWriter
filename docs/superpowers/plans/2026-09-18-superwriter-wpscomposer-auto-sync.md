# SuperWriter / WPSComposer automatic synchronization

**Goal:** Installing the current SuperWriter should resolve and install the current first-party WPSComposer runtime automatically, while preserving an explicit local-source override.

**Architecture:** SuperWriter's installer will use the official WPSComposer Git repository by default. It will keep immutable shallow clones under the user's SuperWriter dependency cache, compare the cached commit with the remote HEAD, and stage all three host references to the selected clone. A failed refresh falls back to the last valid cache; `WPSCOMPOSER_SKILL_SOURCE` remains an offline/local override and is never mutated. The dependency contract and README will describe this behavior.

**Tech Stack:** Python 3 standard library, Git CLI, unittest, JSON contract checks.

## Tasks

- [x] Add failing installer tests for default repository sync, cache reuse/fallback, and explicit-source preservation.
- [x] Implement immutable cached WPSComposer resolution and wire it into the transactional installer and verifier.
- [x] Update dependency guidance and README while keeping the minimum-version contract backward compatible.
- [x] Run focused tests, the full SuperWriter suite, and WPSComposer regression tests.

## Verification

- [x] Explicit `WPSCOMPOSER_SKILL_SOURCE` performs no Git operation.
- [x] Default install stages each host's WPSComposer reference to the selected managed cache.
- [x] Remote refresh failure keeps a valid cached runtime available.
- [x] Existing source and host trees remain transactional and unrelated skills are preserved.
