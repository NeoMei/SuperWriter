"""Real WPS longform output, with separate TOC and native page fields."""

import contextlib
import io
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

try:
    import fitz
except ImportError:
    fitz = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_acceptance import (
    extracted_text, markdown_block_sequence, native_pdf_body_text,
    require_ordered_export_coverage, require_ordered_source_coverage,
)


@unittest.skipUnless(fitz is not None and shutil.which("markitdown"),
                     "requires PyMuPDF and MarkItDown")
class NativePdfTextTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="superwriter-native-pdf-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        shutil.copytree(ROOT / "tests/fixtures/native-longform", self.root, dirs_exist_ok=True)
        self.markdown = (self.root / "manuscript.md").read_text(encoding="utf-8")
        self.pdf = self.root / "native.pdf"

    def verify(self):
        text, furniture_removed = native_pdf_body_text(
            self.pdf, self.root / "native.docx", self.markdown, extracted_text("PDF", self.pdf),
        )
        blocks = markdown_block_sequence(self.markdown)
        require_ordered_source_coverage("PDF", text, blocks)
        require_ordered_export_coverage("PDF", text, blocks,
                                       pdf_page_count=None if furniture_removed else 5)

    def change_pdf(self, change):
        with fitz.open(self.pdf) as document:
            change(document)
            updated = self.root / "updated.pdf"
            document.save(updated)
        updated.replace(self.pdf)

    def assert_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.verify()

    def test_native_toc_running_title_and_page_break_inside_paragraph_are_accepted(self):
        self.verify()

    def test_nonsequential_footer_is_rejected(self):
        def change(document):
            page = document[2]
            page.add_redact_annot(fitz.Rect(290, 779, 320, 796))
            page.apply_redactions()
            page.insert_text((302, 792), "9", fontsize=9)
        self.change_pdf(change)
        self.assert_rejected()

    def test_page_number_in_body_does_not_replace_missing_footer(self):
        def change(document):
            page = document[2]
            page.add_redact_annot(fitz.Rect(290, 779, 320, 796))
            page.apply_redactions()
            page.insert_text((30, 450), "2", fontsize=9)
        self.change_pdf(change)
        self.assert_rejected()

    def test_extra_numeric_body_text_is_rejected(self):
        self.change_pdf(lambda document: document[2].insert_text((30, 450), "2", fontsize=9))
        self.assert_rejected()

    def test_extra_terminal_body_number_equal_to_total_pages_is_rejected(self):
        self.change_pdf(lambda document: document[-1].insert_text((84, 740), "5", fontsize=9))
        self.assert_rejected()

    def test_changed_body_text_is_rejected(self):
        def change(document):
            page = document[2]
            page.add_redact_annot(fitz.Rect(84, 72, 526, 88))
            page.apply_redactions()
        self.change_pdf(change)
        self.assert_rejected()

    def test_wrong_toc_page_reference_is_rejected(self):
        def change(document):
            page = document[0]
            page.add_redact_annot(fitz.Rect(517, 70, 530, 90))
            page.apply_redactions()
            page.insert_text((519, 84), "9", fontsize=9)
        self.change_pdf(change)
        self.assert_rejected()


if __name__ == "__main__":
    unittest.main()
