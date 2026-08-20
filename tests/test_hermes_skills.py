import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = ROOT / "hermes-skills" / "bmad-loop-operations" / "SKILL.md"


class HermesSkillsTest(unittest.TestCase):
    def test_bmad_skill_contract(self) -> None:
        content = SKILL.read_text(encoding="utf-8")
        self.assertIn("name: bmad-loop-operations", content)
        self.assertIn("agent-control", content)
        self.assertIn("Nunca ejecutes BMAD Loop como `root`", content)
        self.assertIn("No reinicies ni reconstruyas el contenedor", content)
        self.assertIn("No memorices estados, PID, run IDs", content)

    def test_references_and_installation_are_wired(self) -> None:
        self.assertTrue((SKILL.parent / "references" / "states-and-evidence.md").is_file())
        self.assertTrue((SKILL.parent / "references" / "safe-recovery.md").is_file())
        self.assertIn("hermes-skills/", (ROOT / "Dockerfile").read_text(encoding="utf-8"))
        self.assertIn("install-hermes-skills", (ROOT / "scripts" / "entrypoint").read_text(encoding="utf-8"))

    def test_sprint_status_is_the_only_story_queue_contract(self) -> None:
        skill_content = SKILL.read_text(encoding="utf-8")
        recovery_content = (SKILL.parent / "references" / "safe-recovery.md").read_text(
            encoding="utf-8"
        )
        workspace_content = (ROOT / "scripts" / "prepare-workspace").read_text(
            encoding="utf-8"
        )
        self.assertIn("cola autoritativa es el `sprint-status.yaml`", skill_content)
        self.assertNotIn("stories.yaml", skill_content + recovery_content)
        self.assertIn('source = "sprint-status"', workspace_content)
        self.assertIn('spec_folder = ""', workspace_content)


if __name__ == "__main__":
    unittest.main()
