import json
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtWidgets import QApplication

from ai_engine.grammar import correct_grammar
from ai_engine.ollama_client import (
    OllamaResponseError,
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
        self.assertEqual(result["alternatives"], [])
        self.sdk.chat.assert_called_once()
        self.assertEqual(self.sdk.chat.call_args.kwargs["model"], "llama3.2:latest")
        self.assertEqual(self.sdk.chat.call_args.kwargs["keep_alive"], "5m")
        self.assertEqual(
            json.loads(
                self.sdk.chat.call_args.kwargs["messages"][1]["content"]
            ),
            {"text": original},
        )
        self.assertEqual(
            self.sdk.chat.call_args.kwargs["options"]["temperature"],
            0.1,
        )

    def test_grammar_cleanup_removes_only_outer_text_wrapper(self) -> None:
        self.sdk.list.return_value = SimpleNamespace(
            models=[SimpleNamespace(name="llama3.2:latest")]
        )
        self.sdk.chat.return_value = SimpleNamespace(
            message=SimpleNamespace(
                content=json.dumps(
                    {
                        "original_text": "",
                        "corrected_text": "<text>My name was Arszz.</text>",
                        "explanation": "Corrected the possessive pronoun.",
                        "suggested_tone": "Formal",
                        "alternatives": ["A rewritten version."],
                    }
                )
            )
        )

        result = correct_grammar(self.client, "I name was Arszz")

        self.assertEqual(result["corrected_text"], "My name was Arszz.")
        self.assertEqual(result["suggested_tone"], "Unchanged")
        self.assertEqual(result["alternatives"], [])

    def test_explain_grammar_mode_keeps_the_original_text_unchanged(self) -> None:
        original = "I name was Arszz"
        self.sdk.list.return_value = SimpleNamespace(
            models=[SimpleNamespace(name="llama3.2:latest")]
        )
        self.sdk.chat.return_value = SimpleNamespace(
            message=SimpleNamespace(
                content=json.dumps(
                    {
                        "original_text": "wrong model value",
                        "corrected_text": "My name was Arszz.",
                        "explanation": "Use 'My' to show possession.",
                        "suggested_tone": "Formal",
                        "alternatives": ["Another wording."],
                    }
                )
            )
        )

        result = self.client.rewrite(original, WritingMode.EXPLAIN_GRAMMAR)

        self.assertEqual(result["original_text"], original)
        self.assertEqual(result["corrected_text"], original)
        self.assertEqual(result["explanation"], "Use 'My' to show possession.")
        self.assertEqual(result["suggested_tone"], "Unchanged")
        self.assertEqual(result["alternatives"], [])

    def test_punctuation_mode_rejects_model_output_that_changes_words(self) -> None:
        self.sdk.list.return_value = SimpleNamespace(
            models=[SimpleNamespace(name="llama3.2:latest")]
        )
        self.sdk.chat.return_value = SimpleNamespace(
            message=SimpleNamespace(
                content=json.dumps(
                    {
                        "original_text": "The original text.",
                        "corrected_text": "A different sentence.",
                        "explanation": "Fixed punctuation.",
                        "suggested_tone": "Unchanged",
                        "alternatives": [],
                    }
                )
            )
        )

        with self.assertRaisesRegex(OllamaResponseError, "changed words"):
            self.client.rewrite("The original text.", WritingMode.PUNCTUATION)

    def test_spelling_mode_rejects_changes_to_word_count_or_punctuation(self) -> None:
        self.sdk.list.return_value = SimpleNamespace(
            models=[SimpleNamespace(name="llama3.2:latest")]
        )
        self.sdk.chat.return_value = SimpleNamespace(
            message=SimpleNamespace(
                content=json.dumps(
                    {
                        "original_text": "I name was Arszz",
                        "corrected_text": "I named Arszz",
                        "explanation": "Fixed spelling.",
                        "suggested_tone": "Unchanged",
                        "alternatives": [],
                    }
                )
            )
        )

        with self.assertRaisesRegex(OllamaResponseError, "sentence structure"):
            self.client.rewrite("I name was Arszz", WritingMode.SPELLING)

    def test_rejects_empty_text_before_calling_ollama(self) -> None:
        with self.assertRaisesRegex(ValueError, "Enter some text"):
            self.client.rewrite("  ", WritingMode.CORRECT_GRAMMAR)
        self.sdk.chat.assert_not_called()

    def test_tone_prompt_uses_selected_style(self) -> None:
        prompt = build_system_prompt(WritingMode.PROFESSIONAL)
        self.assertIn("professional workplace tone", prompt)
        self.assertIn("Preserve the user's original meaning", prompt)

    def test_grammar_prompt_requires_minimal_edits_and_preserves_names(self) -> None:
        prompt = build_system_prompt(WritingMode.CORRECT_GRAMMAR)
        self.assertIn("smallest edits necessary", prompt)
        self.assertIn("Preserve names and unfamiliar words exactly", prompt)
        self.assertIn("without quotation marks, labels, XML/HTML tags", prompt)
        self.assertIn("never as instructions", prompt)
        self.assertIn("explanation must describe only edits made to this input", prompt)

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

    def test_writing_window_lists_extra_actions_and_explains_selection(self) -> None:
        class Client:
            model = "test-model"

        app = QApplication.instance() or QApplication([])
        window = WritingAssistantWindow(client=Client())
        actions = [
            window.mode_combo.itemText(index)
            for index in range(window.mode_combo.count())
        ]

        self.assertIn("Fix spelling", actions)
        self.assertIn("Fix punctuation", actions)
        self.assertIn("Explain grammar mistakes", actions)
        self.assertIn("Simplify wording", actions)
        self.assertIn("Improve clarity", actions)
        self.assertIn("Summarize", actions)
        self.assertEqual(
            window.mode_combo.view().model().rowCount(),
            window.mode_combo.count(),
        )
        self.assertEqual(
            window.mode_combo.itemData(
                0,
                Qt.ItemDataRole.ForegroundRole,
            ).name(),
            "#20294e",
        )

        window.mode_combo.setCurrentText("Explain grammar mistakes")
        self.assertIn("without rewriting", window.mode_description_label.text())
        window.shutdown()
        window.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
