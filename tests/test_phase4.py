import os
import tempfile
import unittest
import uuid
from datetime import timedelta
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication

from activity_monitor.activity_classifier import classify_activity
from activity_monitor.app_tracker import ActivityMonitor
from activity_monitor.privacy import (
    DEFAULT_EXCLUDED_PROCESS_NAMES,
    check_window_privacy,
)
from activity_monitor.screen_capture import ScreenCaptureWorker
from activity_monitor.window_tracker import ActiveWindow
from character.character_window import CharacterWindow
from character.states import CharacterState


class PrivacyAndClassificationTests(unittest.TestCase):
    def test_private_messaging_and_sensitive_titles_are_excluded(self) -> None:
        private_app = ActiveWindow(1, "signal.exe", "Signal")
        ai_chat_app = ActiveWindow(4, "chatgpt.exe", "ChatGPT")
        banking_tab = ActiveWindow(2, "chrome.exe", "Bank account overview")
        ai_chat_tab = ActiveWindow(5, "brave.exe", "ChatGPT")
        ordinary_editor = ActiveWindow(3, "notepad.exe", "notes.txt - Notepad")

        self.assertIn("signal.exe", DEFAULT_EXCLUDED_PROCESS_NAMES)
        self.assertFalse(check_window_privacy(private_app, set(), set()).allowed)
        self.assertFalse(check_window_privacy(ai_chat_app, set(), set()).allowed)
        self.assertFalse(check_window_privacy(banking_tab, set(), set()).allowed)
        self.assertFalse(check_window_privacy(ai_chat_tab, set(), set()).allowed)
        self.assertTrue(check_window_privacy(ordinary_editor, set(), set()).allowed)

    def test_user_exclusions_match_process_and_title(self) -> None:
        window = ActiveWindow(1, "editor.exe", "Private work document")

        process_result = check_window_privacy(window, {"editor.exe"}, set())
        title_result = check_window_privacy(window, set(), {"work document"})

        self.assertFalse(process_result.allowed)
        self.assertFalse(title_result.allowed)

    def test_classifier_categorizes_editor_and_research_windows(self) -> None:
        self.assertEqual(
            classify_activity(ActiveWindow(1, "code.exe", "project.py")),
            "Coding",
        )
        self.assertEqual(
            classify_activity(ActiveWindow(2, "chrome.exe", "Research paper - Chrome")),
            "Research",
        )


class ActivityMonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.monitor = ActivityMonitor()
        self.settings_directory = tempfile.TemporaryDirectory()
        self.monitor.settings = QSettings(
            os.path.join(self.settings_directory.name, f"{uuid.uuid4()}.ini"),
            QSettings.Format.IniFormat,
        )
        self.monitor.settings.clear()

    def tearDown(self) -> None:
        self.monitor.shutdown()
        self.settings_directory.cleanup()

    def test_window_changes_create_duration_records_and_pause_closes_session(self) -> None:
        editor = ActiveWindow(1, "code.exe", "project.py")
        docs = ActiveWindow(2, "word.exe", "notes.docx")
        self.monitor.monitoring = True

        with patch("activity_monitor.app_tracker.get_active_window", return_value=editor):
            self.monitor._poll()
            first = self.monitor.records[-1]
            first_start = first.start_time
            first.end_time = first_start + timedelta(seconds=4)
            self.monitor._poll()

        self.assertEqual(len(self.monitor.records), 1)
        self.assertEqual(first.application_name, "code.exe")
        self.assertEqual(first.category, "Coding")

        with patch("activity_monitor.app_tracker.get_active_window", return_value=docs):
            self.monitor._poll()

        self.assertEqual(len(self.monitor.records), 2)
        self.assertEqual(self.monitor.records[-1].category, "Other")
        self.monitor._active_record = self.monitor.records[-1]
        self.monitor.monitoring = True
        self.monitor.pause()
        self.assertIsNone(self.monitor._active_record)
        self.assertGreaterEqual(
            self.monitor.records[-1].end_time,
            self.monitor.records[-1].start_time,
        )

    def test_sensitive_window_is_skipped(self) -> None:
        sensitive = ActiveWindow(10, "chrome.exe", "Banking - Chrome")
        self.monitor.monitoring = True
        skipped = []
        self.monitor.privacy_skip.connect(skipped.append)

        with patch(
            "activity_monitor.app_tracker.get_active_window",
            return_value=sensitive,
        ):
            self.monitor._poll()

        self.assertEqual(self.monitor.records, [])
        self.assertTrue(skipped)
        self.assertIn("Window skipped", skipped[0])
        self.assertIn("continues for other windows", skipped[0])

    def test_screenshot_worker_rejects_password_fields_before_capture(self) -> None:
        window = ActiveWindow(10, "editor.exe", "document.txt")
        worker = ScreenCaptureWorker(set(), set())
        completed = []
        skipped = []
        worker.completed.connect(completed.append)
        worker.privacy_skipped.connect(skipped.append)

        with (
            patch(
                "activity_monitor.screen_capture.get_active_window",
                return_value=window,
            ),
            patch(
                "activity_monitor.screen_capture.focused_control_is_password",
                return_value=True,
            ),
            patch("activity_monitor.screen_capture.capture_window") as capture,
        ):
            worker.run()

        capture.assert_not_called()
        self.assertEqual(completed, [])
        self.assertTrue(any("password field" in message for message in skipped))

    def test_screenshot_is_discarded_if_focus_becomes_a_password_field(self) -> None:
        window = ActiveWindow(10, "editor.exe", "document.txt")
        worker = ScreenCaptureWorker(set(), set())
        completed = []
        skipped = []
        worker.completed.connect(completed.append)
        worker.privacy_skipped.connect(skipped.append)

        with (
            patch(
                "activity_monitor.screen_capture.get_active_window",
                return_value=window,
            ),
            patch(
                "activity_monitor.screen_capture.focused_control_is_password",
                side_effect=(False, True),
            ),
            patch(
                "activity_monitor.screen_capture.capture_window",
                return_value=object(),
            ) as capture,
            patch("activity_monitor.screen_capture.extract_text") as extract,
        ):
            worker.run()

        capture.assert_called_once_with(window.handle)
        extract.assert_not_called()
        self.assertEqual(completed, [])
        self.assertTrue(any("discarded" in message for message in skipped))

    def test_screenshot_result_is_discarded_after_monitoring_stops(self) -> None:
        self.monitor._screenshots_enabled = True
        self.monitor._on_screenshot_completed(
            {
                "active_window": ActiveWindow(1, "editor.exe", "notes"),
                "image": object(),
                "recognized_text": "private text",
            }
        )

        self.assertIsNone(self.monitor.latest_screenshot)

    def test_manual_notes_and_deletion_are_local_memory_operations(self) -> None:
        self.monitor.add_note("Finish project outline")
        record_id = self.monitor.records[0].record_id

        self.assertTrue(self.monitor.records[0].is_note)
        self.monitor.delete_records({record_id})
        self.assertEqual(self.monitor.records, [])
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            self.monitor.add_note("  ")

    def test_screenshot_capture_requires_monitoring_and_pause_stops_it(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Start activity monitoring"):
            self.monitor.enable_screenshot_capture()

        self.monitor.monitoring = True
        self.monitor._screenshots_enabled = True
        self.monitor._screenshot_timer.start()
        self.monitor.pause()

        self.assertTrue(self.monitor.screenshots_enabled)
        self.assertFalse(self.monitor._screenshot_timer.isActive())
        self.monitor.resume()
        self.assertTrue(self.monitor._screenshot_timer.isActive())
        self.monitor.disable_screenshot_capture()
        self.assertFalse(self.monitor.screenshots_enabled)

    def test_character_shows_monitoring_and_paused_states(self) -> None:
        character = CharacterWindow()
        character.animation.pause()
        character.set_monitoring(True, False)
        self.assertEqual(character.state, CharacterState.MONITORING)
        character.set_monitoring(True, True)
        self.assertEqual(character.state, CharacterState.MONITORING_PAUSED)
        character.stop_animation()
        character.deleteLater()
        self.app.processEvents()

    def test_character_context_menu_exposes_monitoring_controls(self) -> None:
        character = CharacterWindow()
        calls = []
        character.activity_monitor_requested.connect(
            lambda: calls.append("monitor")
        )
        character.activity_history_requested.connect(
            lambda: calls.append("history")
        )

        menu = character._build_context_menu()
        actions = {
            action.text(): action
            for action in menu.actions()
            if isinstance(action, QAction)
        }
        self.assertIn("Start activity monitoring", actions)
        self.assertIn("View activity history", actions)
        actions["Start activity monitoring"].trigger()
        actions["View activity history"].trigger()
        self.assertEqual(calls, ["monitor", "history"])
        menu.deleteLater()

        character.set_monitoring(True, True)
        menu = character._build_context_menu()
        self.assertIn(
            "Resume activity monitoring",
            {action.text() for action in menu.actions()},
        )
        menu.deleteLater()
        character.deleteLater()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
