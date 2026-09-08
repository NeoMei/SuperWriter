# Repository Guidelines

## Project Structure & Module Organization

SuperWriter is a collaborative professional long-form writing skill; its current complete delivery validation is based on tender-response contracts. `SKILL.md` defines its workflow; `references/` holds templates and JSON contracts. `scripts/` contains dependency checks, SVG rendering, and delivery validation. `install.sh` installs skill mirrors into Agents, Claude, and Codex. `tests/` contains regression suites; `验收/` contains simulated customer workspaces, illustrations, and DOCX/PDF examples. Design documents live in `docs/`.

## Build, Test, and Development Commands

Run commands from the repository root. There is no application build or development server.

- `python install.py`: install configured dependency references and host mirrors on macOS/Windows; modifies host skill directories and the Codex routing file. `bash install.sh` and `./install.ps1` are wrappers.
- `python scripts/verify.py`: check dependencies, installed mirrors, routing, and workflow contracts; requires a configured installation.
- `python -m unittest discover -s tests -p 'test_*.py'`: run Python regression tests (macOS may use `python3`).
- `bash tests/test_install.sh`: test transactional installation, rollback, and path safety.
- `bash tests/test_verify_artifacts.sh`: test artifact acceptance and malformed-output rejection.
- `python scripts/verify.py --acceptance-dir <absolute-project-path>`: validate a completed delivery.

Cross-platform verification dependencies are listed in `requirements.txt`. Install them into the verifier's Python environment before running image/PDF suites; verification does not install packages automatically. Use native Windows Python/PowerShell and macOS Python for platform checks. Windows shell-specific legacy tests may be skipped explicitly; portable installation rollback, state contention, rendering and acceptance tests must still run. WPSComposer's OS/backend implementation is owned by its own project; SuperWriter checks its public dependency contract only.

## Coding Style & Naming Conventions

Follow existing formatting: four-space Python indentation, two-space Bash/JavaScript indentation, Python `snake_case`, and uppercase shell configuration variables. Quote shell paths, including Chinese names and spaces. Keep Bash scripts strict with `set -euo pipefail`. No repository-wide formatter or linter is configured. Preserve the public name `SuperWriter` and internal skill ID `superwriter`; update related contracts together.

## Testing Guidelines

Python tests use `unittest`, `test_*.py` files, and `test_*` methods. Add regression cases for changed behavior, especially rejected inputs, rollback, and artifact integrity. No numeric coverage threshold is configured. Run affected suites and report environment-dependent failures separately from passing checks.

## Commit & Pull Request Guidelines

History mixes imperative summaries with `feat:`, `fix:`, and `docs:` prefixes; prefer these prefixes for focused changes. PRs should explain the problem, resulting behavior, affected contracts, and validation commands/results. Link relevant issues or design documents; include rendered evidence when changing document output.

## Agent & Configuration Rules

When `.codegraph/` exists, use `codegraph explore "symbol or file"` before searching or reading code. Otherwise skip CodeGraph.

Structured professional writing requests (tender responses, technical/project proposals, research reports, white papers) first inspect both `流水线状态.md` and `协作状态.json`. New projects use protocol v2 stages `intake / approach / outline / chapters / illustrations / manuscript / delivery`; approach, outline, every chapter, figure set or explicit no-figure decision, and manuscript require explicit current-version user approval. Delivery is machine verified, with layout approval only when a layout object exists. Actual legacy projects continue under `references/legacy-v1`; migration requires an explicit user decision and never invents approvals. Restrict tools and subagents to the current customer's workspace.

Configure dependency sources with `WPSCOMPOSER_SKILL_SOURCE`, `SUPERWRITER_AGENTS_SKILLS_ROOT`, and `SUPERWRITER_OPENCODE_SKILLS_ROOT`; never commit private customer material.
