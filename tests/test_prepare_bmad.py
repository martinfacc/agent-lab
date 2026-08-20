import importlib.util
import os
import pathlib
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "prepare-bmad.py"
SPEC = importlib.util.spec_from_file_location("prepare_bmad", MODULE_PATH)
assert SPEC and SPEC.loader
prepare_bmad = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_bmad)


class PrepareBmadTest(unittest.TestCase):
    def test_accepts_project_relative_artifact_path(self) -> None:
        self.assertEqual(
            prepare_bmad.project_relative("BMAD_OUTPUT_DIR", "docs/bmad"),
            "docs/bmad",
        )

    def test_rejects_absolute_or_parent_artifact_paths(self) -> None:
        for value in ("/tmp/bmad", "../bmad", "docs/../bmad", "C:/bmad"):
            with self.subTest(value=value):
                with self.assertRaises(prepare_bmad.BmadPreparationError):
                    prepare_bmad.project_relative("BMAD_OUTPUT_DIR", value)

    def test_empty_optional_paths_are_derived_from_output(self) -> None:
        environment = {
            "BMAD_OUTPUT_DIR": "docs/agent-artifacts",
            "BMAD_PLANNING_ARTIFACTS_DIR": "",
            "BMAD_IMPLEMENTATION_ARTIFACTS_DIR": "",
        }
        with patch.dict(os.environ, environment, clear=False):
            self.assertEqual(
                prepare_bmad.configured_paths(),
                (
                    "docs/agent-artifacts",
                    "docs/agent-artifacts/planning-artifacts",
                    "docs/agent-artifacts/implementation-artifacts",
                ),
            )


if __name__ == "__main__":
    unittest.main()
