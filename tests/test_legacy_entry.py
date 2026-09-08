"""Check the legacy entry's actual reference resolution, including installed copies."""
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def check_entry(root):
    entry = root / "references/legacy-v1/继续旧项目.md"
    text = entry.read_text(encoding="utf-8")
    assert "references/legacy-v1/继续旧项目.md" in (root / "SKILL.md").read_text()
    rows = dict(re.findall(r"^\| `([^`]+)` \| `([^`]+)` \|$", text, re.M))
    frozen = root / "references/legacy-v1"
    skill = (frozen / "SKILL.md").read_text()
    refs = set(re.findall(r"references/[^`\s)]+", skill))
    assert set(rows) == refs, (rows, refs)
    changed = {"阶段契约.json", "门禁清单.md", "验收清单模板.json"}
    provenance = json.loads((frozen / "source.json").read_text())
    for original, target in rows.items():
        name = Path(original).name
        expected = f"references/legacy-v1/{name}" if name in changed else original
        assert target == expected, (original, target)
        path = root / target
        assert path.is_file(), path
        if name in changed:
            assert hashlib.sha256(path.read_bytes()).hexdigest() == provenance["files"][original]
    contract = json.loads((root / rows["references/阶段契约.json"]).read_text())
    assert contract["version"] == 1
    assert [row["stage"] for row in contract["stages"]] == list(range(10))
    assert [row["stage"] for row in contract["stages"] if row["interaction"] == "human"] == [2, 5, 8]
    template = json.loads((root / rows["references/验收清单模板.json"]).read_text())
    assert template["version"] == 1
    assert template["pipeline"]["human_gates"] == [2, 5, 8]
    assert hashlib.sha256((frozen / "SKILL.md").read_bytes()).hexdigest() == provenance["files"]["SKILL.md"]


class LegacyEntryTest(unittest.TestCase):
    def test_legacy_reference_resolution_preserves_v1_semantics(self):
        check_entry(ROOT)


if __name__ == "__main__":
    check_entry(Path(sys.argv[1]))
    print("PASS: installed legacy reference resolution and v1 continuation contracts")
