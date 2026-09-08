"""Real WPS delivery regressions for missing or altered PDF illustrations."""

from pathlib import Path
import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import fitz
except ImportError:
    fitz = None


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_acceptance import validate_pdf_figures


class PdfFigureDependencyTest(unittest.TestCase):
    def test_missing_pymupdf_reports_actionable_dependency_error(self):
        stderr = io.StringIO()
        with mock.patch.dict(sys.modules, {"fitz": None}), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit):
                validate_pdf_figures(Path("not-opened.pdf"), [object()])
        self.assertIn("requires PyMuPDF", stderr.getvalue())

    def test_no_figure_delivery_does_not_require_image_extraction(self):
        with mock.patch.dict(sys.modules, {"fitz": None}):
            validate_pdf_figures(Path("not-opened.pdf"), [])


@unittest.skipUnless(
    fitz is not None and shutil.which("markitdown"),
    "native PDF acceptance requires PyMuPDF and MarkItDown",
)
class PdfFigureAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="superwriter-pdf-test-")
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "project"
        shutil.copytree(ROOT / "验收/协作写作-v2-模拟", self.project)
        # Use the real, approved state immediately before delivery was recorded;
        # output hashes must be established by acceptance, not pretrusted here.
        shutil.copyfile(
            self.project / "evidence/18-delivery-v3-rebound-to-manuscript-v4.json",
            self.project / "协作状态.json",
        )
        shutil.copyfile(
            self.project / "evidence/19-acceptance-manifest-revision-62.json",
            self.project / "验收清单.json",
        )
        self.pdf = self.project / "导出/协作审阅试点技术方案.pdf"

    def verify(self):
        return subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts/verify_acceptance.py"),
            str(self.project)], capture_output=True, text=True, encoding="utf-8",
        )

    def change_pdf(self, change):
        with fitz.open(self.pdf) as document:
            change(document)
            updated = self.pdf.with_name("updated.pdf")
            document.save(updated)
        updated.replace(self.pdf)

    def assert_rejected_figure(self):
        result = self.verify()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("PDF expected diagram", result.stderr)

    def test_real_wps_pdf_preserves_approved_illustration(self):
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_pdf_image_is_rejected_even_when_caption_and_text_survive(self):
        def remove(document):
            for page in document:
                for image in page.get_images():
                    page.delete_image(image[0])
        self.change_pdf(remove)
        self.assert_rejected_figure()

    def test_changed_pdf_image_is_rejected_even_with_original_dimensions(self):
        def replace(document):
            page = document[0]
            xref = page.get_images()[0][0]
            replacement = fitz.Pixmap(document, xref)
            replacement.clear_with(255)
            page.replace_image(xref, pixmap=replacement)
        self.change_pdf(replace)
        self.assert_rejected_figure()

    def test_unused_pdf_image_resource_does_not_prove_visible_illustration(self):
        def remove_paint(document):
            for page in document:
                for image in page.get_images():
                    name = image[7].encode("ascii")
                    for stream in page.get_contents():
                        payload = document.xref_stream(stream)
                        document.update_stream(stream, payload.replace(b"/" + name + b" Do", b""))
        self.change_pdf(remove_paint)
        with fitz.open(self.pdf) as document:
            self.assertTrue(document[0].get_images())
            self.assertFalse(document[0].get_image_info())
        self.assert_rejected_figure()

    def test_white_overlay_hiding_painted_image_is_rejected(self):
        def cover(document):
            for page in document:
                for info in page.get_image_info():
                    page.draw_rect(fitz.Rect(info["bbox"]), fill=(1, 1, 1),
                                   color=None, overlay=True)
        self.change_pdf(cover)
        self.assert_rejected_figure()


if __name__ == "__main__":
    unittest.main()
