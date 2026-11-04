import ctypes
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QPoint, QTimer
from PySide6.QtWidgets import QApplication

from text_assistant.selection import (
    SelectionCaptureWorker,
    SelectionUnavailableError,
)
from text_assistant.shortcuts import GlobalShortcut, HOTKEY_ID, WM_HOTKEY
from text_assistant.writing_window import WritingAssistantWindow
import text_assistant.shortcuts as shortcuts


class SelectionCaptureWorkerTests(unittest.TestCase):
    def test_worker_emits_selected_text_without_logging_or_transforming_it(self) -> None:
        class Reader:
            def read_selection(self, target_window: int) -> str:
                self.target_window = target_window
                return "Selected text."

        reader = Reader()
        worker = SelectionCaptureWorker(1234, QPoint(30, 40), reader)
        received = []
        worker.selection_ready.connect(
            lambda text, hwnd, point: received.append((text, hwnd, point))
        )

        worker.run()

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0], "Selected text.")
        self.assertEqual(received[0][1], 1234)
        self.assertEqual(received[0][2], QPoint(30, 40))
        self.assertEqual(reader.target_window, 1234)

    def test_worker_surfaces_unsupported_selection_to_ui(self) -> None:
        class Reader:
            def read_selection(self, target_window: int) -> str:
                raise SelectionUnavailableError("Selection is unavailable.")

        worker = SelectionCaptureWorker(1234, QPoint(30, 40), Reader())
        errors = []
        worker.selection_failed.connect(
            lambda message, hwnd, point: errors.append((message, hwnd, point))
        )

        worker.run()

        self.assertEqual(errors, [("Selection is unavailable.", 1234, QPoint(30, 40))])


class GlobalShortcutTests(unittest.TestCase):
    def test_native_filter_reads_qt_void_pointer_and_dispatches_hotkey(self) -> None:
        calls = []
        shortcut = GlobalShortcut.__new__(GlobalShortcut)
        shortcuts.QAbstractNativeEventFilter.__init__(shortcut)
        shortcut._callback = lambda: calls.append("called")

        message = shortcuts._Message()
        message.message = WM_HOTKEY
        message.wParam = HOTKEY_ID

        class QtVoidPointer:
            def __int__(self) -> int:
                return ctypes.addressof(message)

        handled, result = shortcut.nativeEventFilter(
            b"windows_generic_MSG",
            QtVoidPointer(),
        )

        self.assertTrue(handled)
        self.assertEqual(result, 0)
        self.assertEqual(calls, ["called"])


class SelectionWritingWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        class Client:
            model = "test-model"

        self.window = WritingAssistantWindow(client=Client())
        self.window._model_checked = True

    def tearDown(self) -> None:
        self.window.shutdown()
        self.window.hide()
        self.window.deleteLater()
        self.app.processEvents()

    def test_selection_is_loaded_and_replace_requires_an_actual_suggestion(self) -> None:
        self.window.show_selection("Selected sentence.", 1234, QPoint(20, 20))

        self.assertEqual(self.window.input_edit.toPlainText(), "Selected sentence.")
        self.assertTrue(self.window.replace_button.isVisible())
        self.assertFalse(self.window.replace_button.isEnabled())

        self.window._on_result_ready(
            {
                "corrected_text": "Corrected sentence.",
                "explanation": "Grammar fixed.",
                "suggested_tone": "Neutral",
                "alternatives": [],
            }
        )

        self.assertTrue(self.window.replace_button.isEnabled())

    def test_clipboard_fallback_is_explicit_and_never_arms_replace(self) -> None:
        self.window.show_selection(
            "",
            1234,
            QPoint(20, 20),
            "UI Automation could not read this selection.",
        )
        self.app.clipboard().setText("Copied text.")

        self.window.paste_from_clipboard()

        self.assertEqual(self.window.input_edit.toPlainText(), "Copied text.")
        self.assertFalse(self.window.replace_button.isVisible())
        self.assertFalse(self.window._replace_allowed)
        self.assertIn("Replacement is disabled", self.window.status_label.text())

    def test_selection_error_is_displayed_without_becoming_replaceable_text(self) -> None:
        self.window.show_selection_error(
            "This control does not expose a selection.",
            1234,
            QPoint(20, 20),
        )

        self.assertEqual(self.window.input_edit.toPlainText(), "")
        self.assertFalse(self.window.replace_button.isVisible())
        self.assertFalse(self.window._replace_allowed)
        self.assertIn("does not expose", self.window.status_label.text())

    def test_manual_assistant_does_not_keep_stale_replacement_target(self) -> None:
        self.window.show_selection("Selected sentence.", 1234, QPoint(20, 20))
        self.window.show_and_focus()

        self.assertIsNone(self.window._target_window_handle)
        self.assertFalse(self.window.replace_button.isVisible())

    def test_confirmed_selection_triggers_default_grammar_suggestion(self) -> None:
        class Client:
            model = "test-model"

            def rewrite(self, text, mode):
                return {
                    "original_text": text,
                    "corrected_text": "Corrected selection.",
                    "explanation": "Grammar fixed.",
                    "suggested_tone": "Neutral",
                    "alternatives": [],
                }

        self.window._client = Client()
        self.window._model_checked = True
        loop = QEventLoop()
        self.window.processing_changed.connect(
            lambda busy: loop.quit()
            if not busy and "SUGGESTED TEXT" in self.window.output_edit.toPlainText()
            else None
        )
        QTimer.singleShot(5000, loop.quit)

        self.window.present_selection_and_suggest(
            "Selected sentence.", 1234, QPoint(20, 20)
        )
        loop.exec()

        self.assertIn("Corrected selection.", self.window.output_edit.toPlainText())
        self.assertEqual(self.window.input_edit.toPlainText(), "Selected sentence.")
        self.assertTrue(self.window.replace_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
