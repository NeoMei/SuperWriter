# Native longform fixture

Synthetic source and DOCX/PDF generated through the real WPSComposer public API on macOS on 2026-09-08. The five-page PDF contains a TOC with Roman page numbering, three body chapters with Arabic page numbering, a running title and one diagram.

`manuscript.md` and `配图/` preserve the complete source. `native.docx` and `native.pdf` are immutable regression inputs; tests operate on temporary copies. WPS page-render evidence is in `验收/发布后审查-20260908/WPS五页实物检查/`.

The test suite verifies native text and page furniture against these real outputs. It does not launch WPS or claim user approval. All content is synthetic.
