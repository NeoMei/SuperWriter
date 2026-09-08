"""The portable verifier must accept the unchanged previously approved delivery."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ExistingDeliveryPortabilityTest(unittest.TestCase):
    def test_existing_approved_delivery_remains_valid_without_rebinding_hashes(self):
        with tempfile.TemporaryDirectory(prefix="superwriter-existing-delivery-") as temporary:
            project = Path(temporary) / "客户 中文项目"
            shutil.copytree(ROOT / "验收/协作写作-v2-模拟", project)
            approved = {
                path.relative_to(project): path.read_bytes()
                for path in project.rglob("*")
                if path.is_file() and path.suffix.lower() in {".png", ".svg", ".docx", ".pdf"}
            }
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/verify_acceptance.py"), str(project)],
                cwd=project, text=True, encoding="utf-8", capture_output=True, timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS: explicit acceptance manifest", result.stdout)
            for relative, payload in approved.items():
                self.assertEqual((project / relative).read_bytes(), payload)
