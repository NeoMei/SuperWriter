from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReviewUIRegressionTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is required for the review UI network harness")
    def test_async_review_actions_and_image_rendering(self):
        result = subprocess.run(
            ["node", str(ROOT / "tests/review_ui_harness.js"),
             str(ROOT / "scripts/review_assets/review.js")],
            text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("PASS "), 5)
