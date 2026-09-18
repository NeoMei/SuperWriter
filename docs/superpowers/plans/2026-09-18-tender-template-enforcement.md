# 招标模板与版式强制验收实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 protocol v2 的投标交付必须绑定已核验的版式契约；招标文件提供 Office 格式模板时，复制模板并以模板的稳定排版部件作为生成文档基准，输出未真正继承模板时阻断交付。

**Architecture:** 在现有 `checks.layout` 上增加显式的 `template` 分支：`copy` 表示项目内模板文件及 SHA-256，`none` 表示已经核验招标文件未提供可复用 Office 模板。验收器在投标 v2 交付时强制存在并验证 layout，在 `copy` 模式下验证模板文件、模板摘要和输出 DOCX 的稳定 OOXML 部件；正文段落和字符实际格式逐项检查，不只依赖默认样式。SuperWriter 只依赖 WPSComposer 公开契约；公开接口没有模板输入能力时记录为导出阻塞，不调用私有参数。

**Tech Stack:** Python 3.12+, `unittest`, JSON contracts, DOCX ZIP/XML inspection, WPSComposer public API.

**Spec:** 用户关于“补齐版式验收缺口；招标文件有格式模板时复制模板并让后续文档套用模板格式”的要求，以及 `references/招标响应结构模板.md` 和 `references/协作交付验收.md` 的投标交付规则。

## Global Constraints

- legacy-v1 文件和验收契约保持冻结；本次强制门禁只作用于 protocol v2 的 `document_type: tender`。
- protocol v2 投标交付必须有 `checks.layout`；`layout.template.mode` 必须是 `copy` 或 `none`。
- `copy` 模式只接受项目内普通文件，使用模板实际 SHA-256；支持 `.docx` 与 `.dotx`，输出必须是基于该模板的 `.docx`。
- 模板存在时不得使用 WPSComposer preset 覆盖模板；WPSComposer 不提供模板输入时不得伪造通过。
- 所有生产代码先有会失败的回归测试；使用 `apply_patch` 编辑文件；工作区保持客户材料不进入提交。
- 版本统一为 0.2.9，安装镜像和 GitHub Release 在本计划完成后单独处理。

---

### Task 1: 扩展版式与模板契约

**Files:**
- Modify: `references/结构化核验.md`
- Modify: `references/结构化核验模板.json`
- Modify: `scripts/collaboration/checks.py`
- Test: `tests/test_outline_structure_regressions.py`

**Interfaces:**
- `layout.template` exact shape: `{"mode": "copy", "path": str, "sha256": str, "format": "docx"|"dotx"}` or `{"mode": "none", "reason": str}`.
- `validate_checks()` rejects a layout missing `template` or containing unknown template fields.

- [ ] **Step 1: Write failing schema tests** for missing template, invalid mode, unsafe/nonempty path rules, invalid digest, and valid `copy`/`none` variants.
- [ ] **Step 2: Run `python3 -m unittest tests.test_outline_structure_regressions -v`** and confirm the new tests fail because the existing schema has no template contract.
- [ ] **Step 3: Implement the exact template schema and documentation.** Keep the existing page, page-number, and typography validation; add format and 64-hex digest validation.
- [ ] **Step 4: Re-run the focused schema tests** and confirm all pass.
- [ ] **Step 5: Commit** with `feat: add tender template binding contract`.

### Task 2: Add template copy and stable-package verification

**Files:**
- Create: `scripts/tender_template.py`
- Test: `tests/test_tender_template.py`

**Interfaces:**
- `resolve_template(project_root: Path, spec: dict) -> Path`: rejects traversal, symlink, directory, unsupported suffix, missing file, and digest mismatch.
- `copy_template(project_root: Path, spec: dict, destination: Path) -> Path`: copies the verified template atomically into the requested project-relative destination and returns the destination.
- `verify_template_application(template: Path, output: Path) -> None`: requires the output DOCX to retain template stable parts (`word/styles.xml`, `word/numbering.xml`, `word/settings.xml`, `word/fontTable.xml`, `word/theme/theme1.xml`, and all template header/footer parts) byte-for-byte; mutable document and metadata parts are excluded.

- [ ] **Step 1: Write failing tests** using tiny ZIP-based DOCX fixtures for valid resolution/copy, traversal rejection, digest mismatch, missing stable part, and changed stable part.
- [ ] **Step 2: Run `python3 -m unittest tests.test_tender_template -v`** and confirm the tests fail because the module does not exist.
- [ ] **Step 3: Implement safe path resolution, SHA-256 verification, atomic copy, and stable OOXML package comparison.** Treat `.dotx` as an accepted source but require the generated output to be `.docx`.
- [ ] **Step 4: Re-run the focused template tests** and confirm all pass.
- [ ] **Step 5: Commit** with `feat: verify copied tender templates`.

### Task 3: Enforce layout and template checks in v2 tender acceptance

**Files:**
- Modify: `scripts/verify_acceptance.py`
- Test: `tests/test_verify_acceptance.py`
- Test: `tests/test_collaboration_acceptance.py`

**Interfaces:**
- `verify_tender_layout(docx_path, layout, native_page_contract, project_root=None) -> None` remains callable by existing tests and additionally verifies actual paragraph/run font, size, and line spacing wherever direct properties are present; inherited values resolve through the style chain.
- `verify_tender_template(project_root, docx_path, template_spec) -> None` delegates to `tender_template.py`.

- [ ] **Step 1: Write failing acceptance tests** for a tender v2 delivery without layout, a layout without template, a template output whose stable style part changed, and a body paragraph/run that overrides the approved font or size.
- [ ] **Step 2: Run the focused acceptance tests** and confirm they fail for the missing enforcement and default-style-only behavior.
- [ ] **Step 3: Make `main()` require a verified layout for v2 tender acceptance.** Keep professional and legacy-v1 behavior unchanged. Require `template.mode=copy` verification when selected and `template.mode=none` only with a nonempty recorded reason.
- [ ] **Step 4: Extend DOCX typography checking** to resolve paragraph and run direct properties plus inherited paragraph-style properties; reject any substantive body paragraph/run that differs from the declared body typography. Preserve heading-specific style exceptions by checking body paragraphs and direct runs, not title/heading paragraphs.
- [ ] **Step 5: Re-run the focused acceptance tests** and confirm all pass.
- [ ] **Step 6: Commit** with `fix: enforce tender layout and template inheritance`.

### Task 4: Make template-first generation explicit in guidance and fixtures

**Files:**
- Modify: `SKILL.md`
- Modify: `references/招标响应结构模板.md`
- Modify: `references/协作交付验收.md`
- Modify: `references/结构化核验模板.json`
- Modify: `references/验收清单模板.json`
- Modify: `README.md`
- Test: `tests/test_workflow_contract.py`

- [ ] **Step 1: Add guidance tests** asserting the public workflow says to copy a supplied DOCX/DOTX template into the project, bind its SHA-256, use it as the WPSComposer base, omit design presets, and stop when the public WPSComposer contract cannot apply it.
- [ ] **Step 2: Run the guidance tests** and confirm they fail before the text changes.
- [ ] **Step 3: Update the guidance and JSON examples.** Add a template-first sequence: preserve original template bytes, copy to a project-relative template path, generate from that base, then run template-package and layout checks. State that a tender with no Office template must record `mode: none` plus the source review reason.
- [ ] **Step 4: Update the acceptance template** so new v2 tender projects include `document_type: tender` and a complete layout/template skeleton.
- [ ] **Step 5: Re-run guidance and workflow tests** and confirm all pass.
- [ ] **Step 6: Commit** with `docs: require template-first tender generation`.

### Task 5: Synchronize version and run the complete verification gate

**Files:**
- Modify: `SKILL.md`
- Modify: `references/依赖清单.json`
- Modify: `scripts/check_dependencies.py`
- Modify: `README.md`

- [ ] **Step 1: Update the synchronized version from 0.2.8 to 0.2.9.**
- [ ] **Step 2: Run focused schema/template/acceptance tests.**
- [ ] **Step 3: Run `python3 -m unittest discover -s tests -p 'test_*.py'`.**
- [ ] **Step 4: Run `bash tests/test_install.sh` and `bash tests/test_verify_artifacts.sh`.**
- [ ] **Step 5: Run `python3 scripts/verify.py`.**
- [ ] **Step 6: Review `git diff --check`, inspect the final diff, and record any WPS native/template capability limitation explicitly.
- [ ] **Step 7: Commit** with `chore: prepare SuperWriter 0.2.9 release`.

## Review Checklist

- [ ] Missing layout cannot pass a v2 tender delivery.
- [ ] Missing or invalid template declaration cannot pass a new layout contract.
- [ ] A supplied template is copied, hash-bound, and its stable OOXML parts survive into the output.
- [ ] Direct body formatting overrides are caught even when the default paragraph style matches.
- [ ] Professional documents and legacy-v1 remain unaffected.
- [ ] All tests and portable installation/artifact gates pass in the default Python 3.12 environment.
