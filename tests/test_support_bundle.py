import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "support-bundle.py"
SPEC = importlib.util.spec_from_file_location("support_bundle", SCRIPT)
assert SPEC and SPEC.loader
support_bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(support_bundle)


class SupportBundleTests(unittest.TestCase):
    def test_redacts_named_and_environment_secrets(self) -> None:
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123:private"}):
            result = support_bundle.sanitize(
                "token=visible TELEGRAM_BOT_TOKEN=123:private"
            )
        self.assertNotIn("visible", result)
        self.assertNotIn("123:private", result)
        self.assertIn("[REDACTADO]", result)

    def test_journal_summary_excludes_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            journal = Path(temporary) / "journal.jsonl"
            journal.write_text(
                json.dumps(
                    {
                        "ts": 1,
                        "kind": "session-start",
                        "story_key": "2-1",
                        "prompt": "contenido privado",
                    }
                ),
                encoding="utf-8",
            )
            result = support_bundle.journal_summary(journal)
        self.assertIn("session-start", result)
        self.assertNotIn("contenido privado", result)
        self.assertNotIn("prompt", result)


if __name__ == "__main__":
    unittest.main()
