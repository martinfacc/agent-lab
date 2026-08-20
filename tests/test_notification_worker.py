import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "notification-worker.py"
SPEC = importlib.util.spec_from_file_location("notification_worker", MODULE_PATH)
assert SPEC and SPEC.loader
notification_worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notification_worker)


class NotificationWorkerTests(unittest.TestCase):
    def test_classifies_attention_titles(self) -> None:
        self.assertEqual(notification_worker.classify("story awaiting operator"), "awaiting-operator")
        self.assertEqual(notification_worker.classify("story gated"), "paused")
        self.assertEqual(notification_worker.classify("auto sweep failed"), "crashed")
        self.assertEqual(notification_worker.classify("bmad-loop run finished"), "finished")

    def test_first_scan_does_not_replay_existing_notifications(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            attention = Path(directory) / "run-1" / "ATTENTION"
            attention.parent.mkdir()
            attention.write_text("[2026-08-20 10:00:00] run finished: viejo\n", encoding="utf-8")
            offsets: dict[str, int] = {}
            with patch.object(notification_worker, "dispatch") as dispatch:
                notification_worker.process_file(attention, offsets, initialize=True)
                dispatch.assert_not_called()
                with attention.open("a", encoding="utf-8") as handle:
                    handle.write("[2026-08-20 10:01:00] story gated: necesita revisión\n")
                notification_worker.process_file(attention, offsets, initialize=False)
                dispatch.assert_called_once_with("run-1", "story gated", "necesita revisión")

    def test_dispatch_respects_channel_and_event_filters(self) -> None:
        environment = {"NOTIFY_CHANNELS": "telegram,ntfy", "NOTIFY_EVENTS": "finished"}
        with patch.dict(os.environ, environment, clear=False), patch.object(
            notification_worker, "send_telegram"
        ) as telegram, patch.object(notification_worker, "send_ntfy") as ntfy:
            notification_worker.dispatch("run-1", "bmad-loop run finished", "ok")
            telegram.assert_called_once()
            ntfy.assert_called_once()

    def test_read_only_status_command_uses_latest_run(self) -> None:
        state = {
            "run_id": "run-1",
            "status": "paused",
            "current_epic": 2,
            "paused_stage": "epic-boundary",
            "tasks": {"story-1": {"story_key": "story-1", "phase": "done"}},
        }
        with patch.object(notification_worker, "select_run", return_value=state):
            response = notification_worker.handle_command("123", "/estado", {})
        self.assertIn("Run: run-1", response)
        self.assertIn("Estado: paused", response)

    def test_controlled_action_requires_one_time_confirmation(self) -> None:
        state = {"run_id": "run-1", "status": "paused"}
        pending: dict[str, dict[str, object]] = {}
        with patch.dict(os.environ, {"TELEGRAM_COMMANDS": "controlled"}), patch.object(
            notification_worker, "select_run", return_value=state
        ):
            response = notification_worker.handle_command("123", "/reanudar", pending)
        self.assertIn("/confirmar_resume", response)
        code = str(pending["123"]["code"])
        with patch.object(notification_worker, "execute_action", return_value="ok") as action:
            confirmed = notification_worker.handle_command(
                "123", f"/confirmar_resume {code}", pending
            )
        self.assertEqual(confirmed, "ok")
        action.assert_called_once_with("resume", "run-1")
        self.assertNotIn("123", pending)

    def test_translates_worktree_failure_into_actionable_message(self) -> None:
        title, body = notification_worker.friendly_notification(
            "run-1",
            "worktree open failed",
            "1-1-mi-story: fatal: internal git details",
        )
        self.assertEqual(title, "No se pudo iniciar una story")
        self.assertIn("La story no comenzó", body)
        self.assertIn("Qué hacer:", body)
        self.assertNotIn("fatal:", body)

    def test_translates_run_summary_without_token_noise(self) -> None:
        title, body = notification_worker.friendly_notification(
            "run-1",
            "bmad-loop run finished",
            "run run-1: 2 done, 1 deferred, 0 escalated, 999 weighted tokens",
        )
        self.assertEqual(title, "La ejecución terminó con tareas pendientes")
        self.assertIn("Completadas: 2", body)
        self.assertIn("Pendientes: 1", body)
        self.assertNotIn("tokens", body)

    def test_keeps_multiline_attention_record_together(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            attention = Path(directory) / "run-1" / "ATTENTION"
            attention.parent.mkdir()
            attention.write_text(
                "[2026-08-20 10:00:00] bmad-loop run finished: resumen\n"
                "PAUSED: epic 1 boundary\n",
                encoding="utf-8",
            )
            with patch.object(notification_worker, "dispatch") as dispatch:
                notification_worker.process_file(attention, {}, initialize=False)
            dispatch.assert_called_once_with(
                "run-1", "bmad-loop run finished", "resumen\nPAUSED: epic 1 boundary"
            )


if __name__ == "__main__":
    unittest.main()
