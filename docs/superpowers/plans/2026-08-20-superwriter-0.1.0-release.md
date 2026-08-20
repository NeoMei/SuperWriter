# SuperWriter 0.1.0 Release and Dependency Guidance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish SuperWriter `0.1.0`, define and enforce its WPSComposer/third-party skill dependencies, guide users through installing every prerequisite, and synchronize the verified release to GitHub and three local skill hosts.

**Architecture:** A machine-readable dependency manifest is the single source of dependency identity, purpose, source root, minimum version, and installation guidance. A Python preflight checker consumes that manifest before any installer mutation; `install.sh` and `scripts/verify.sh` share the checker, while README/SKILL present the same contract to humans and agents.

**Tech Stack:** Agent Skills Markdown/YAML, JSON, Python 3.9+, Bash, Git, GitHub CLI, WPSComposer `0.7.2`.

## Global Constraints

- SuperWriter release version is exactly `0.1.0`; internal skill ID remains exactly `superwriter`; display name remains exactly `SuperWriter`.
- WPSComposer is a first-party runtime dependency with minimum version `0.7.2`; do not modify or republish WPSComposer in this plan.
- External skills are exactly `grilling`, `grill-me`, `grill-with-docs`, `to-spec`, `domain-modeling`, `ai-image-to-ppt`, and `obsidian-excalidraw`.
- Do not publish, vendor, or invent repository URLs for third-party skill source code.
- Do not silently download dependencies; report all missing dependencies together before mutating any host.
- Preserve the three target hosts: `~/.agents/skills`, `~/.claude/skills`, and `~/.codex/skills`.
- Preserve source overrides: `SUPERWRITER_AGENTS_SKILLS_ROOT`, `SUPERWRITER_OPENCODE_SKILLS_ROOT`, and `WPSCOMPOSER_SKILL_SOURCE`.
- Preserve transaction rollback, path safety, customer confidentiality, stage/gate contracts, and WPSComposer-only DOCX/PDF generation.
- Commit only confirmed SuperWriter release files; exclude `.codegraph/`, customer workspaces, generated bids, and unrelated files.
- Publish through a PR to GitHub `main`; only after merged-main verification create annotated tag and GitHub Release `v0.1.0`.

---

### Task 1: Validate and Commit Existing Naming and Portable-Path Changes

**Files:**
- Modify: `README.md`
- Modify: `SKILL.md`
- Modify: `docs/environment-check.md`
- Modify: `install.sh`
- Modify: `scripts/verify.sh`
- Modify: `tests/test_install.sh`
- Modify: `tests/test_verify_artifacts.sh`
- Modify: `验收/验收报告.md`

**Interfaces:**
- Consumes: the current eight-file working-tree diff already approved as release scope.
- Produces: canonical public name `SuperWriter`, internal ID `superwriter`, and portable sibling lookup for `WPSComposer`/`WpsComposer` with regression evidence.

- [ ] **Step 1: Capture the exact pre-task scope**

Run:

```bash
git status -sb
git diff --name-only
git diff --check
```

Expected: exactly the eight files above are modified; `.codegraph/` is untracked; no whitespace errors.

- [ ] **Step 2: Reconstruct RED against the committed baseline in a temporary directory**

```bash
release_red_dir="$(mktemp -d /tmp/superwriter-release-red.XXXXXX)"
git archive HEAD | tar -x -C "$release_red_dir"
cp tests/test_install.sh "$release_red_dir/tests/test_install.sh"
cp tests/test_verify_artifacts.sh "$release_red_dir/tests/test_verify_artifacts.sh"
chmod +x "$release_red_dir/tests/test_install.sh" "$release_red_dir/tests/test_verify_artifacts.sh"
(cd "$release_red_dir" && bash tests/test_install.sh)
(cd "$release_red_dir" && bash tests/test_verify_artifacts.sh)
```

Expected: at least one test fails because committed-baseline installer/README/SKILL still use the old public casing or machine-specific WPS path. Record the exact failing assertion. Remove the temporary directory after recording evidence.

- [ ] **Step 3: Run the current implementation GREEN**

```bash
bash tests/test_install.sh
bash tests/test_verify_artifacts.sh
git diff --check
```

Expected: both test scripts exit 0 and print their pass summaries; diff check exits 0.

- [ ] **Step 4: Review the eight-file diff for scope**

```bash
git diff -- README.md SKILL.md docs/environment-check.md install.sh scripts/verify.sh tests/test_install.sh tests/test_verify_artifacts.sh 验收/验收报告.md
git status --short
```

Expected: only naming, portable sibling lookup, their tests, and matching report wording; `.codegraph/` remains unstaged.

- [ ] **Step 5: Commit only the validated files**

```bash
git add -- README.md SKILL.md docs/environment-check.md install.sh scripts/verify.sh tests/test_install.sh tests/test_verify_artifacts.sh 验收/验收报告.md
git commit -m "Harden SuperWriter naming and portable installation"
```

Expected: one commit with the eight files; `git status --short` shows only `?? .codegraph/`.

---

### Task 2: Add Version and Machine-Readable Dependency Contract

**Files:**
- Create: `references/依赖清单.json`
- Create: `tests/test_dependency_contract.py`
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `references/门禁清单.md`

**Interfaces:**
- Consumes: canonical name/ID from Task 1.
- Produces: dependency manifest schema version 1, SuperWriter version `0.1.0`, WPSComposer floor `0.7.2`, seven external skill records, and matching human/agent documentation.

- [ ] **Step 1: Run the skill retrieval RED before editing**

Give a fresh-context subagent only the current `SKILL.md` and this prompt:

```text
You must install SuperWriter completely on a new Mac. List the exact SuperWriter version, the minimum WPSComposer version, every external skill dependency, each default source root and override variable, and what the installer does when multiple dependencies are missing. Do not infer facts not present in the supplied skill.
```

Expected RED: the response cannot name SuperWriter `0.1.0`, WPSComposer `0.7.2`, the full seven-skill set with source roots, or aggregate/non-mutating failure behavior because the current skill does not contain that contract. Save the verbatim response under ignored `.superpowers/sdd/task-2-skill-red.md`.

- [ ] **Step 2: Write failing manifest tests**

Create `tests/test_dependency_contract.py` with exact assertions:

```python
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DependencyContractTest(unittest.TestCase):
    def test_dependency_manifest_matches_release_contract(self):
        manifest = json.loads((ROOT / "references" / "依赖清单.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["superwriter_version"], "0.1.0")
        by_id = {item["id"]: item for item in manifest["dependencies"]}
        self.assertEqual(set(by_id), {
            "WPSComposer", "grilling", "grill-me", "grill-with-docs",
            "to-spec", "domain-modeling", "ai-image-to-ppt", "obsidian-excalidraw",
        })
        self.assertEqual(by_id["WPSComposer"]["kind"], "first-party-runtime")
        self.assertEqual(by_id["WPSComposer"]["minimum_version"], "0.7.2")
        self.assertEqual(by_id["WPSComposer"]["environment"], "WPSCOMPOSER_SKILL_SOURCE")
        self.assertEqual(by_id["obsidian-excalidraw"]["source_root"], "opencode")
        self.assertEqual(by_id["obsidian-excalidraw"]["environment"], "SUPERWRITER_OPENCODE_SKILLS_ROOT")
        for skill_id in set(by_id) - {"WPSComposer", "obsidian-excalidraw"}:
            self.assertEqual(by_id[skill_id]["kind"], "third-party-skill")
            self.assertEqual(by_id[skill_id]["source_root"], "agents")
            self.assertEqual(by_id[skill_id]["environment"], "SUPERWRITER_AGENTS_SKILLS_ROOT")
            self.assertNotIn("github.com", by_id[skill_id]["install_hint"])

    def test_skill_and_readme_publish_the_same_versions_and_dependency_ids(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("version: 0.1.0", skill)
        self.assertIn("v0.1.0 (2026-08-20)", readme)
        self.assertIn("WPSComposer `0.7.2`", skill)
        manifest = json.loads((ROOT / "references" / "依赖清单.json").read_text(encoding="utf-8"))
        for dependency in manifest["dependencies"]:
            self.assertIn(dependency["id"], skill)
            self.assertIn(dependency["id"], readme)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests to verify RED**

```bash
python3 tests/test_dependency_contract.py
```

Expected: FAIL because `references/依赖清单.json` and the version/dependency documentation do not exist.

- [ ] **Step 4: Add the minimum manifest and documentation**

Create `references/依赖清单.json` with this shape for every dependency:

```json
{
  "schema_version": 1,
  "superwriter_version": "0.1.0",
  "dependencies": [
    {
      "id": "WPSComposer",
      "kind": "first-party-runtime",
      "required": true,
      "purpose": "WPS native DOCX/PDF generation and layout",
      "source_root": "wps",
      "environment": "WPSCOMPOSER_SKILL_SOURCE",
      "minimum_version": "0.7.2",
      "install_hint": "git clone https://github.com/NeoMei/WPSComposer.git, then set WPSCOMPOSER_SKILL_SOURCE"
    }
  ]
}
```

Add all seven external skill objects with `required: true`, concise purposes, the exact source roots/environments from the tests, and generic trusted-skill-manager hints without repository URLs. Add `version: 0.1.0` to SKILL frontmatter, an “安装依赖” section to `SKILL.md`, a dependency matrix plus `v0.1.0 (2026-08-20)` release entry to README, and a dependency-preflight item to `references/门禁清单.md`.

- [ ] **Step 5: Verify GREEN and skill retrieval GREEN**

```bash
python3 tests/test_dependency_contract.py
```

Expected: all Task 2 tests pass.

Rerun the Step 1 prompt with the updated `SKILL.md`. Expected GREEN: exact versions, all seven external skills, WPSComposer, source roots, override variables, and aggregate/no-mutation behavior are all present without invented third-party URLs. Save the response under ignored `.superpowers/sdd/task-2-skill-green.md`.

- [ ] **Step 6: Commit the dependency contract**

```bash
git add -- SKILL.md README.md references/依赖清单.json references/门禁清单.md tests/test_dependency_contract.py
git commit -m "Define SuperWriter 0.1.0 dependency contract"
```

Expected: one focused commit; `.codegraph/` remains untracked.

---

### Task 3: Add Aggregate, Non-Mutating Dependency Preflight

**Files:**
- Create: `scripts/check_dependencies.py`
- Modify: `install.sh`
- Modify: `scripts/verify.sh`
- Modify: `tests/test_install.sh`
- Modify: `tests/test_verify_artifacts.sh`
- Test: `tests/test_dependency_contract.py`

**Interfaces:**
- Consumes: `references/依赖清单.json` from Task 2.
- Produces command:

```text
python3 scripts/check_dependencies.py \
  --manifest references/依赖清单.json \
  --agents-root PATH \
  --opencode-root PATH \
  --wps-source PATH
```

Exit 0 means every source is usable. Exit 2 means one or more dependencies are missing, incomplete, or below an available version floor; stderr contains every finding and actionable guidance. A standalone WPSComposer skill with no repository metadata passes capability validation and emits a version-metadata warning.

- [ ] **Step 1: Add failing checker and installer behavior tests**

Extend `tests/test_dependency_contract.py` to invoke the checker in temporary roots and assert:

```python
assert result.returncode == 2
for missing in ["grilling", "domain-modeling", "obsidian-excalidraw", "WPSComposer"]:
    assert missing in result.stderr
assert "No host files were changed" in result.stderr
```

Extend `tests/test_install.sh` with fixtures that:

1. remove multiple source skills simultaneously and assert all names plus both source-root variables appear;
2. snapshot three host roots and `AGENTS.md`, run the failing installer, then assert byte-for-byte hashes unchanged;
3. provide a WPSComposer repo fixture with `.codex-plugin/plugin.json` version `0.7.1` and assert rejection naming minimum `0.7.2`;
4. provide version `0.7.2` and assert success;
5. provide a standalone complete WPSComposer skill without repository metadata and assert success plus the explicit capability-contract warning.

Extend `tests/test_verify_artifacts.sh` to reject a manifest with a missing dependency, duplicate ID, wrong source root, invented third-party GitHub URL, or WPSComposer minimum other than `0.7.2`.

- [ ] **Step 2: Run focused tests to verify RED**

```bash
python3 tests/test_dependency_contract.py
bash tests/test_install.sh
bash tests/test_verify_artifacts.sh
```

Expected: new cases fail because the checker and aggregate preflight do not exist.

- [ ] **Step 3: Implement `check_dependencies.py`**

Implement these pure boundaries:

```python
def load_manifest(path: Path) -> dict: ...
def validate_manifest(data: dict) -> list[str]: ...
def parse_version(value: str) -> tuple[int, int, int]: ...
def find_wps_repository_root(skill_dir: Path) -> Path | None: ...
def read_wps_version(skill_dir: Path) -> str | None: ...
def inspect_dependencies(data: dict, agents_root: Path, opencode_root: Path, wps_source: Path) -> tuple[list[str], list[str]]: ...
def format_failure(findings: list[str], manifest: dict) -> str: ...
```

Validate exact schema/IDs, required `SKILL.md`, WPS runtime capability anchor `scripts/macos_probe`, repository metadata when available, and generic third-party hints. Do not mutate any path.

- [ ] **Step 4: Call preflight before installer mutation**

In `install.sh`, resolve source roots and WPS candidate without creating host directories, then invoke the checker before `mktemp`, snapshots, `mkdir`, moves, symlinks, or route staging. On exit 2, forward the complete guidance and exit unchanged. After preflight succeeds, continue the existing transaction using the same resolved sources.

In `scripts/verify.sh`, validate the dependency manifest and source environment through the same checker before exact installed-manifest checks.

- [ ] **Step 5: Run focused GREEN and full repository regression**

```bash
python3 tests/test_dependency_contract.py
bash tests/test_install.sh
bash tests/test_verify_artifacts.sh
bash scripts/verify.sh
```

Expected: all commands exit 0. The static verifier names SuperWriter `0.1.0`, WPSComposer `0.7.2` when metadata is available, and every required external skill.

- [ ] **Step 6: Commit the preflight implementation**

```bash
git add -- scripts/check_dependencies.py install.sh scripts/verify.sh tests/test_dependency_contract.py tests/test_install.sh tests/test_verify_artifacts.sh
git commit -m "Guide and verify SuperWriter dependencies"
```

Expected: one focused commit with production code and RED/GREEN tests.

---

### Task 4: Complete Repository Verification and Review

**Files:**
- Verify: all files changed from `origin/main` to `HEAD`
- Preserve untracked: `.codegraph/`

**Interfaces:**
- Consumes: Tasks 1–3 commits.
- Produces: a reviewed release branch with no open Critical, Important, or Minor findings.

- [ ] **Step 1: Run all release gates**

```bash
python3 tests/test_dependency_contract.py
bash tests/test_install.sh
bash tests/test_verify_artifacts.sh
bash scripts/verify.sh
bash scripts/verify.sh --acceptance-dir "$PWD/验收/模拟客户A/模拟标段1"
git diff --check origin/main...HEAD
```

Expected: every command exits 0; acceptance verifies the example project; no warnings or partial skips.

- [ ] **Step 2: Verify release scope and versions**

```bash
git status -sb
git diff --name-only origin/main...HEAD
python3 - <<'PY'
import json
from pathlib import Path
root = Path('.')
skill = (root / 'SKILL.md').read_text(encoding='utf-8')
manifest = json.loads((root / 'references/依赖清单.json').read_text(encoding='utf-8'))
assert 'version: 0.1.0' in skill
assert manifest['superwriter_version'] == '0.1.0'
assert next(item for item in manifest['dependencies'] if item['id'] == 'WPSComposer')['minimum_version'] == '0.7.2'
print('RELEASE_CONTRACT_PASS')
PY
```

Expected: `.codegraph/` is the only untracked path; no customer or WPSComposer repository files appear in the diff.

- [ ] **Step 3: Perform task reviews and whole-branch review**

Use fresh reviewers for each task and a final whole-branch reviewer. Review requirements include installation no-mutation, dependency aggregation, version fallback honesty, third-party ownership wording, skill discovery, rollback, test validity, shell portability, and release scope. Fix every Critical/Important finding and repeat review; for this release, also close all actionable Minor findings.

- [ ] **Step 4: Write the reviewed PR body, then push and create one ready PR**

Create ignored `.superpowers/sdd/superwriter-0.1.0-pr.md` with this exact structure:

```markdown
## What changed
- release SuperWriter 0.1.0 with canonical public naming and portable WPSComposer discovery
- add a machine-readable dependency contract and aggregate non-mutating preflight
- guide installation of WPSComposer 0.7.2 and seven external skills without vendoring or silent downloads

## Validation
- dependency-contract test
- installer regression
- artifact/acceptance regression
- static and example acceptance verification

## Deployment
After merged-main verification, publish tag/Release v0.1.0 and install the exact release to three local hosts.
```

```bash
git push -u origin codex/superwriter-0.1.0-release
gh pr create --base main --head codex/superwriter-0.1.0-release \
  --title "Release SuperWriter 0.1.0 with dependency guidance" \
  --body-file .superpowers/sdd/superwriter-0.1.0-pr.md
```

Expected: one non-draft PR targeting `main`; body describes version, dependencies, no-silent-download rule, tests, and local deployment plan.

- [ ] **Step 5: Merge only after the PR is clean**

```bash
pr_number="$(gh pr view codex/superwriter-0.1.0-release --json number --jq .number)"
gh pr view "$pr_number" --json state,isDraft,mergeable,mergeStateStatus,statusCheckRollup,url
gh pr merge "$pr_number" --merge --delete-branch
```

Expected: PR state becomes `MERGED`; merge commit exists on `origin/main`; remote feature branch is deleted.

---

### Task 5: Publish Tag/Release and Synchronize Local Skill Hosts

**Files:**
- Deploy from: final GitHub `main`
- Update local installed roots only through: `install.sh`

**Interfaces:**
- Consumes: verified merged `main` from Task 4.
- Produces: tag and GitHub Release `v0.1.0`, and three exact local host installations of SuperWriter `0.1.0` plus declared dependencies.

- [ ] **Step 1: Verify merged main before tagging**

```bash
git fetch origin --prune
git switch main
git pull --ff-only origin main
bash tests/test_install.sh
bash tests/test_verify_artifacts.sh
python3 tests/test_dependency_contract.py
```

Expected: all tests pass on `main`; local `HEAD` equals `origin/main`.

- [ ] **Step 2: Write reviewed release notes, then create the annotated tag and GitHub Release**

Create ignored `.superpowers/sdd/superwriter-0.1.0-release-notes.md` containing:

```markdown
SuperWriter 0.1.0 formalizes the nine-stage technical-bid workflow, canonical naming, portable WPSComposer discovery, and non-mutating dependency preflight.

Required runtime: WPSComposer 0.7.2 or newer.

External skills: grilling, grill-me, grill-with-docs, to-spec, domain-modeling, ai-image-to-ppt, obsidian-excalidraw. Install them from sources you trust into the documented source roots; SuperWriter does not vendor or silently download them.

Install with `bash install.sh`; override source roots with `SUPERWRITER_AGENTS_SKILLS_ROOT`, `SUPERWRITER_OPENCODE_SKILLS_ROOT`, and `WPSCOMPOSER_SKILL_SOURCE`. Verify with `bash scripts/verify.sh`.
```

```bash
git tag -a v0.1.0 -m "SuperWriter 0.1.0"
git push origin v0.1.0
gh release create v0.1.0 --title "SuperWriter 0.1.0" --notes-file .superpowers/sdd/superwriter-0.1.0-release-notes.md
```

Release notes must list SuperWriter version, WPSComposer `0.7.2`, all seven external skills, source-root overrides, installation command, verification commands, and the no-vendoring/no-silent-download boundary.

- [ ] **Step 3: Install from final main into all three hosts**

```bash
WPSCOMPOSER_SKILL_SOURCE=/Users/neomei/项目/codexprojects/WpsComposer/skills/WPSComposer \
  bash install.sh
bash scripts/verify.sh
```

Expected: installer reports all dependency sources and completes one transaction; verifier passes exact manifests for `.agents`, `.claude`, and `.codex`.

- [ ] **Step 4: Verify installed versions and exact dependency copies**

```bash
python3 - <<'PY'
from pathlib import Path
hosts = [Path.home()/'.agents/skills', Path.home()/'.claude/skills', Path.home()/'.codex/skills']
dependencies = ['superwriter','grilling','grill-me','grill-with-docs','to-spec','domain-modeling','ai-image-to-ppt','obsidian-excalidraw','WPSComposer']
for host in hosts:
    skill = (host/'superwriter/SKILL.md').read_text(encoding='utf-8')
    assert 'version: 0.1.0' in skill
    for dependency in dependencies:
        assert (host/dependency/'SKILL.md').is_file(), (host, dependency)
print('THREE_HOST_RELEASE_PASS')
PY
```

- [ ] **Step 5: Verify live GitHub release state and WPSComposer relationship**

```bash
gh release view v0.1.0 --json tagName,name,isDraft,isPrerelease,url,targetCommitish
git ls-remote --tags origin refs/tags/v0.1.0
gh api 'repos/NeoMei/SuperWriter/contents/SKILL.md?ref=main' --jq '.content' | base64 --decode | grep -F 'version: 0.1.0'
gh api 'repos/NeoMei/WPSComposer/contents/.codex-plugin/plugin.json?ref=master' --jq '.content' | base64 --decode | grep -F '"version": "0.7.2"'
```

Expected: release is published, non-draft, non-prerelease; tag points to merged `main`; remote SuperWriter is `0.1.0`; WPSComposer remains `0.7.2`.

- [ ] **Step 6: Run final installed-skill acceptance**

Run the same dependency-retrieval prompt from Task 2 against `/Users/neomei/.codex/skills/superwriter/SKILL.md`. Expected: exact versions, dependencies, source roots, override variables, and failure behavior. Run `bash scripts/verify.sh --acceptance-dir "$PWD/验收/模拟客户A/模拟标段1"` once more and require exit 0.
