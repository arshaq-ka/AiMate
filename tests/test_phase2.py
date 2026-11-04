import json
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from ai_engine.grammar import correct_grammar
from ai_engine.ollama_client import (
    OllamaUnavailableError,
    OllamaWritingClient,
)
from ai_engine.prompts import WritingMode, build_system_prompt
from ai_engine.tone import improve_tone
from text_assistant.writing_window import WritingAssistantWindow


class OllamaWritingClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sdk = Mock()
        self.client = OllamaWritingClient(
            client=self.sdk,
            model=None,
        )

    def test_selects_installed_llama_32_model(self) -> None:
        self.sdk.list.return_value = SimpleNamespace(
            models=[
                SimpleNamespace(name="nomic-embed-text:latest"),
                SimpleNamespace(name="llama3.2:latest"),
            ]
        )

        self.assertEqual(self.client.check_model(), "llama3.2:latest")

    def test_reports_clear_error_when_no_supported_model_is_installed(self) -> None:
        self.sdk.list.return_value = SimpleNamespace(
            models=[SimpleNamespace(name="nomic-embed-text:latest")]
        )

        with self.assertRaisesRegex(OllamaUnavailableError, "ollama pull"):
            self.client.check_model()

    def test_refuses_remote_ollama_host_to_protect_local_text(self) -> None:
        with self.assertRaisesRegex(ValueError, "loopback host"):
            OllamaWritingClient(host="http://example.com:11434", client=self.sdk)

    def test_grammar_response_is_structured_and_preserves_input(self) -> None:
        original = "I am not able to attend meeting because i have some work."
        self.sdk.list.return_value = SimpleNamespace(
            models=[SimpleNamespace(name="llama3.2:latest")]
        )
        self.sdk.chat.return_value = SimpleNamespace(
            message=SimpleNamespace(
                content=json.dumps(
                    {
                        "original_text": "model altered this field",
                        "corrected_text": (
                            "I am unable to attend the meeting because I have "
                            "some work to do."
                        ),
                        "explanation": "Corrected grammar and capitalization.",
                        "suggested_tone": "Neutral",
                        "alternatives": ["I cannot attend the meeting."],
                    }
                )
            )
        )

        result = correct_grammar(self.client, original)

        self.assertEqual(result["original_text"], original)
        self.assertEqual(
            result["corrected_text"],
            "I am unable to attend the meeting because I have some work to do.",
        )
        self.assertEqual(result["alternatives"], ["I cannot attend the meeting."])
        self.sdk.chat.assert_called_once()
        self.assertEqual(self.sdk.chat.call_args.kwargs["model"], "llama3.2:latest")
        self.assertEqual(self.sdk.chat.call_args.kwargs["keep_alive"], "5m")

    def test_rejects_empty_text_before_calling_ollama(self) -> None:
        with self.assertRaisesRegex(ValueError, "Enter some text"):
            self.client.rewrite("  ", WritingMode.CORRECT_GRAMMAR)
        self.sdk.chat.assert_not_called()

    def test_tone_prompt_uses_selected_style(self) -> None:
        prompt = build_system_prompt(WritingMode.PROFESSIONAL)
        self.assertIn("professional workplace tone", prompt)
        self.assertIn("Preserve the user's original meaning", prompt)

    def test_tone_helper_rejects_grammar_only_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "grammar operation"):
            improve_tone(
                self.client,
                "Some text",
                WritingMode.CORRECT_GRAMMAR,
            )

    def test_writing_window_keeps_ui_responsive_during_generation(self) -> None:
        class SlowClient:
            model = "mock-local-model"

            def rewrite(self, text: str, mode: WritingMode) -> dict[str, object]:
                time.sleep(0.15)
                return {
                    "original_text": text,
                    "corrected_text": "A corrected sentence.",
                    "explanation": "Fixed the grammar.",
                    "suggested_tone": "Neutral",
                    "alternatives": ["An alternative sentence."],
                }

        app = QApplication.instance() or QApplication([])
        window = WritingAssistantWindow(client=SlowClient())
        window._model_checked = True
        window.input_edit.setPlainText("An sentence.")
        loop = QEventLoop()
        ui_timer_fired = []
        window.processing_changed.connect(
            lambda busy: loop.quit() if not busy and ui_timer_fired else None
        )
        QTimer.singleShot(0, lambda: ui_timer_fired.append(True))
        QTimer.singleShot(5000, loop.quit)

        window.request_suggestion()
        loop.exec()

        self.assertTrue(ui_timer_fired)
        self.assertIn("A corrected sentence.", window.output_edit.toPlainText())
        self.assertTrue(window.copy_button.isEnabled())
        window.shutdown()
        window.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
