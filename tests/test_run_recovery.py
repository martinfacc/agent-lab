import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "run-recovery.py"
SPEC = importlib.util.spec_from_file_location("run_recovery", SCRIPT)
assert SPEC and SPEC.loader
run_recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_recovery)


class RunRecoveryTests(unittest.TestCase):
    def test_finds_only_unfinished_runs_without_live_processes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runs = Path(temporary)
            interrupted = runs / "run-interrupted"
            interrupted.mkdir()
            (interrupted / "state.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-interrupted",
                        "tasks": [{"story_key": "2-1", "phase": "dev-running"}],
                    }
                ),
                encoding="utf-8",
            )
            finished = runs / "run-finished"
            finished.mkdir()
            (finished / "state.json").write_text(
                json.dumps({"run_id": "run-finished", "finished": True}), encoding="utf-8"
            )
            with mock.patch.object(run_recovery, "RUNS_DIR", runs), mock.patch.object(
                run_recovery, "engine_alive", return_value=False
            ), mock.patch.object(run_recovery, "tmux_alive", return_value=False):
                result = run_recovery.orphaned_runs()
            self.assertEqual([item["run_id"] for item in result], ["run-interrupted"])
            self.assertTrue(result[0]["recoverable"])

    def test_does_not_classify_paused_run_as_orphaned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run-paused"
            run_dir.mkdir()
            (run_dir / "state.json").write_text(
                json.dumps({"run_id": "run-paused", "paused_reason": "epic boundary"}),
                encoding="utf-8",
            )
            with mock.patch.object(run_recovery, "RUNS_DIR", Path(temporary)):
                self.assertEqual(run_recovery.orphaned_runs(), [])


if __name__ == "__main__":
    unittest.main()
