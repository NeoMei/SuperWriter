from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.tender_template import (
    TemplateError,
    copy_template,
    resolve_template,
    verify_template_application,
)


class TenderTemplateTest(unittest.TestCase):
    def write_package(self, path: Path, *, style: bytes = b"style", include_header: bool = True) -> str:
        members = {
            "word/styles.xml": style,
            "word/numbering.xml": b"numbering",
            "word/settings.xml": b"settings",
            "word/fontTable.xml": b"fonts",
            "word/theme/theme1.xml": b"theme",
            "word/document.xml": b"document",
        }
        if include_header:
            members["word/header1.xml"] = b"header"
            members["word/footer1.xml"] = b"footer"
        with zipfile.ZipFile(path, "w") as archive:
            for name, payload in members.items():
                archive.writestr(name, payload)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def copy_spec(self, path: str, digest: str) -> dict:
        return {"mode": "copy", "path": path, "sha256": digest, "format": Path(path).suffix[1:]}

    def test_resolve_and_copy_template_binds_actual_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "来源.docx"
            digest = self.write_package(source)
            spec = self.copy_spec("来源.docx", digest)
            resolved = resolve_template(root, spec)
            destination = root / "模板" / "投标格式.docx"
            copied = copy_template(root, spec, destination)
            self.assertEqual(resolved.resolve(), source.resolve())
            self.assertEqual(copied.resolve(), destination.resolve())
            self.assertEqual(destination.read_bytes(), source.read_bytes())

    def test_resolve_rejects_path_traversal_and_digest_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "来源.docx"
            digest = self.write_package(source)
            with self.assertRaisesRegex(TemplateError, "project-relative"):
                resolve_template(root, self.copy_spec("../来源.docx", digest))
            with self.assertRaisesRegex(TemplateError, "sha256"):
                resolve_template(root, self.copy_spec("来源.docx", "0" * 64))

    def test_verify_template_application_rejects_missing_or_changed_stable_part(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "模板.docx"
            output = root / "输出.docx"
            digest = self.write_package(template)
            output.write_bytes(template.read_bytes())
            verify_template_application(template, output)

            self.write_package(output, style=b"changed")
            with self.assertRaisesRegex(TemplateError, "stable template part differs"):
                verify_template_application(template, output)

            with zipfile.ZipFile(output, "w") as archive:
                archive.writestr("word/document.xml", b"document")
            with self.assertRaisesRegex(TemplateError, "stable template part is missing"):
                verify_template_application(template, output)


if __name__ == "__main__":
    unittest.main()
