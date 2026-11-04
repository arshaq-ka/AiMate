import logging
from typing import Any

from PySide6.QtCore import QObject, QThread, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ai_engine.grammar import correct_grammar
from ai_engine.ollama_client import OllamaWritingClient
from ai_engine.prompts import WritingMode
from ai_engine.tone import improve_tone
from text_assistant.selection import replace_selection_in_window

logger = logging.getLogger(__name__)


class WritingWorker(QObject):
    model_checked = Signal(str)
    result_ready = Signal(object)
    error_occurred = Signal(str)
    finished = Signal()

    def __init__(
        self,
        client: OllamaWritingClient,
        task: str,
        text: str = "",
        mode: WritingMode | None = None,
    ) -> None:
        super().__init__()
        self._client = client
        self._task = task
        self._text = text
        self._mode = mode

    def run(self) -> None:
        try:
            if self._task == "check":
                self.model_checked.emit(self._client.check_model())
            elif self._task == "rewrite":
                if self._mode is WritingMode.CORRECT_GRAMMAR:
                    result = correct_grammar(self._client, self._text)
                else:
                    result = improve_tone(
                        self._client,
                        self._text,
                        self._mode or WritingMode.IMPROVE_TONE,
                    )
                self.result_ready.emit(result)
            else:
                raise ValueError(f"Unknown writing task: {self._task}")
        except Exception as exc:
            logger.exception("Writing assistant request failed")
            self.error_occurred.emit(str(exc))
        finally:
            self.finished.emit()


class WritingAssistantWindow(QDialog):
    processing_changed = Signal(bool)

    def __init__(
        self,
        client: OllamaWritingClient | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Local Writing Assistant")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumSize(540, 620)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._client = client or OllamaWritingClient()
        self._thread: QThread | None = None
        self._worker: WritingWorker | None = None
        self._model_checked = False
        self._last_corrected_text = ""
        self._target_window_handle: int | None = None
        self._replace_allowed = False
        self._selection_notice: str | None = None
        self._auto_suggest_pending = False
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background: #f5f7ff; color: #26315f; }
            QLabel#heading { font-size: 20px; font-weight: 700; color: #373878; }
            QLabel#status { color: #555f86; padding: 4px; }
            QPlainTextEdit, QComboBox {
                background: white; border: 1px solid #d5daf0;
                border-radius: 8px; padding: 8px; color: #20294e;
            }
            QPushButton {
                background: #7069e8; color: white; border: none;
                border-radius: 8px; padding: 9px 14px; font-weight: 600;
            }
            QPushButton:disabled { background: #b8b8cf; color: #f6f6fa; }
            QPushButton#secondary { background: #e5e8fb; color: #373878; }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(10)

        heading = QLabel("Local Writing Assistant")
        heading.setObjectName("heading")
        layout.addWidget(heading)
        layout.addWidget(
            QLabel(
                "Your text is processed by Ollama on this computer. "
                "Suggestions are shown for review; your text is never replaced."
            )
        )

        self.status_label = QLabel("Checking local Ollama when this window opens…")
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText("Paste or type text to improve…")
        self.input_edit.setTabChangesFocus(True)
        layout.addWidget(self.input_edit, 3)

        self.mode_combo = QComboBox()
        self._mode_by_index: list[WritingMode] = []
        for mode in WritingMode:
            self.mode_combo.addItem(mode.value)
            self._mode_by_index.append(mode)
        layout.addWidget(self.mode_combo)

        controls = QHBoxLayout()
        self.check_button = QPushButton("Check Ollama")
        self.check_button.setObjectName("secondary")
        self.check_button.clicked.connect(self.check_ollama)
        controls.addWidget(self.check_button)
        controls.addStretch(1)
        self.run_button = QPushButton("Get suggestion")
        self.run_button.clicked.connect(self.request_suggestion)
        controls.addWidget(self.run_button)
        layout.addLayout(controls)

        self.output_edit = QPlainTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setPlaceholderText(
            "The suggested text, explanation, tone, and alternatives will appear here."
        )
        layout.addWidget(self.output_edit, 2)

        bottom_controls = QHBoxLayout()
        self.copy_button = QPushButton("Copy corrected text")
        self.copy_button.setObjectName("secondary")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self.copy_corrected_text)
        bottom_controls.addWidget(self.copy_button)
        self.replace_button = QPushButton("Replace selected text")
        self.replace_button.setObjectName("secondary")
        self.replace_button.setVisible(False)
        self.replace_button.setEnabled(False)
        self.replace_button.clicked.connect(self.replace_selected_text)
        bottom_controls.addWidget(self.replace_button)
        self.clipboard_button = QPushButton("Paste from clipboard")
        self.clipboard_button.setObjectName("secondary")
        self.clipboard_button.clicked.connect(self.paste_from_clipboard)
        bottom_controls.addWidget(self.clipboard_button)
        bottom_controls.addStretch(1)
        layout.addLayout(bottom_controls)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt event override
        super().showEvent(event)
        if not self._model_checked and self._thread is None:
            self.check_ollama()

    def show_and_focus(self) -> None:
        self._target_window_handle = None
        self._replace_allowed = False
        self._auto_suggest_pending = False
        self.replace_button.setVisible(False)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input_edit.setFocus()

    def show_selection(
        self,
        text: str,
        target_window: int,
        anchor: QPoint,
        notice: str | None = None,
    ) -> None:
        self._auto_suggest_pending = False
        self._target_window_handle = target_window or None
        self._replace_allowed = bool(text)
        self._selection_notice = notice if not text else None
        self.input_edit.setPlainText(text)
        self.replace_button.setVisible(bool(text and target_window))
        self.replace_button.setEnabled(False)
        self._last_corrected_text = ""
        self.copy_button.setEnabled(False)
        self.output_edit.clear()

        if text:
            self.status_label.setText(
                "Selected text loaded. Choose an operation and review the "
                "suggestion before copying or replacing."
            )
        elif notice:
            self.status_label.setText(notice)
        else:
            self.status_label.setText(
                "No selected text was available. You can paste it from the "
                "clipboard below."
            )

        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            right = max(area.left(), area.right() - self.width() + 1)
            bottom = max(area.top(), area.bottom() - self.height() + 1)
            x = min(max(anchor.x() + 16, area.left()), right)
            y = min(max(anchor.y() + 16, area.top()), bottom)
            self.move(x, y)

        self.show()
        self.raise_()
        self.activateWindow()
        if text:
            self.input_edit.setFocus()
        else:
            self.clipboard_button.setFocus()

    def present_selection_and_suggest(
        self,
        text: str,
        target_window: int,
        anchor: QPoint,
    ) -> None:
        self.show_selection(text, target_window, anchor)
        if not text:
            return
        self._auto_suggest_pending = True
        if self._model_checked and self._thread is None:
            QTimer.singleShot(0, self._start_pending_suggestion)

    def _start_pending_suggestion(self) -> None:
        if (
            self._auto_suggest_pending
            and self._model_checked
            and self._thread is None
        ):
            self._auto_suggest_pending = False
            self.request_suggestion()

    def show_selection_error(
        self,
        message: str,
        target_window: int,
        anchor: QPoint,
    ) -> None:
        self.show_selection("", target_window, anchor, notice=message)

    def paste_from_clipboard(self) -> None:
        text = QApplication.clipboard().text()
        if not text:
            self.status_label.setText("The clipboard does not contain any text.")
            return
        self.input_edit.setPlainText(text)
        self._replace_allowed = False
        self.replace_button.setVisible(False)
        self.status_label.setText(
            "Clipboard text pasted into the assistant. Replacement is disabled "
            "because the source selection was not confirmed."
        )

    def check_ollama(self) -> None:
        if self._thread is not None:
            return
        self.status_label.setText("Checking the local Ollama service and model…")
        self.check_button.setEnabled(False)
        self.run_button.setEnabled(False)
        self._start_worker("check")

    def request_suggestion(self) -> None:
        if self._thread is not None:
            return
        text = self.input_edit.toPlainText()
        mode = self._mode_by_index[self.mode_combo.currentIndex()]
        self.output_edit.clear()
        self.copy_button.setEnabled(False)
        self._last_corrected_text = ""
        self.replace_button.setEnabled(False)
        self.status_label.setText("Thinking…")
        self.run_button.setEnabled(False)
        self.check_button.setEnabled(False)
        self.processing_changed.emit(True)
        self._start_worker("rewrite", text, mode)

    def _start_worker(
        self,
        task: str,
        text: str = "",
        mode: WritingMode | None = None,
    ) -> None:
        thread = QThread(self)
        worker = WritingWorker(self._client, task, text, mode)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.model_checked.connect(self._on_model_checked)
        worker.result_ready.connect(self._on_result_ready)
        worker.error_occurred.connect(self._on_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_model_checked(self, model: str) -> None:
        self._model_checked = True
        message = f"Connected to local Ollama • {model}"
        if self._selection_notice:
            message = f"{message} • {self._selection_notice}"
        self.status_label.setText(message)

    def _on_result_ready(self, result: dict[str, Any]) -> None:
        self._last_corrected_text = result["corrected_text"]
        lines = [
            "SUGGESTED TEXT",
            result["corrected_text"],
            "",
            "EXPLANATION",
            result["explanation"],
            "",
            "SUGGESTED TONE",
            result["suggested_tone"],
        ]
        if result["alternatives"]:
            lines.extend(["", "ALTERNATIVES"])
            lines.extend(
                f"{index}. {alternative}"
                for index, alternative in enumerate(result["alternatives"], start=1)
            )
        self.output_edit.setPlainText("\n".join(lines))
        self.copy_button.setEnabled(bool(self._last_corrected_text))
        self.replace_button.setEnabled(
            bool(
                self._last_corrected_text
                and self._target_window_handle
                and self._replace_allowed
            )
        )
        self.status_label.setText(
            f"Suggestion ready • {self._client.model or 'local model'}"
        )

    def _on_error(self, message: str) -> None:
        self.status_label.setText(f"Unable to complete the request: {message}")

    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self.check_button.setEnabled(True)
        self.run_button.setEnabled(self._model_checked)
        if self.status_label.text() == "Thinking…":
            self.status_label.setText("Request finished.")
        self.processing_changed.emit(False)
        if self._auto_suggest_pending and self._model_checked:
            QTimer.singleShot(0, self._start_pending_suggestion)

    def copy_corrected_text(self) -> None:
        if self._last_corrected_text:
            QApplication.clipboard().setText(self._last_corrected_text)
            self.status_label.setText("Suggested text copied to the clipboard.")

    def replace_selected_text(self) -> None:
        if (
            not self._target_window_handle
            or not self._replace_allowed
            or not self._last_corrected_text
        ):
            self.status_label.setText(
                "There is no confirmed selection to replace. Copy the suggestion "
                "or paste text into the original application manually."
            )
            return
        try:
            replace_selection_in_window(
                self._target_window_handle,
                self._last_corrected_text,
            )
        except (OSError, ValueError) as exc:
            self.status_label.setText(f"Could not replace the selection: {exc}")
            return

        self._replace_allowed = False
        self.replace_button.setEnabled(False)
        self.status_label.setText(
            "The selected text was replaced in the original application."
        )

    def shutdown(self) -> None:
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        event.ignore()
        self.hide()
