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


if __name__ == "__main__":
    unittest.main()
