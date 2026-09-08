"""Malformed review envelopes fail with controlled errors before state mutation."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from scripts.collaboration.model import CollaborationError
from scripts.collaboration.store import commit_event, initialize


class ModelBoundaryRegressionTest(unittest.TestCase):
    def test_nonstring_event_enums_are_controlled_errors_without_state_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = initialize(root, "synthetic-malformed-events")
            before = (root / "协作状态.json").read_bytes()
            event = {
                "id": "malformed-event", "kind": "record_preference",
                "object_id": None, "version": None, "sha256": None,
                "channel": "chat",
                "evidence": {"reference": "synthetic-test", "text": "prefer concise"},
                "payload": {"scope": "project", "text": "prefer concise"},
            }
            for field in ("kind", "channel"):
                for value in ([], {}):
                    with self.subTest(field=field, value=value):
                        malformed = deepcopy(event)
                        malformed[field] = value
                        with self.assertRaisesRegex(CollaborationError, f"event {field}"):
                            commit_event(root, malformed, state["revision"])
                        self.assertEqual((root / "协作状态.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
