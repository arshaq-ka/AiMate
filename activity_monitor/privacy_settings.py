from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)

from activity_monitor.app_tracker import ActivityMonitor
from activity_monitor.privacy import DEFAULT_EXCLUDED_PROCESS_NAMES


class PrivacySettingsDialog(QDialog):
    def __init__(self, monitor: ActivityMonitor, parent=None) -> None:
        super().__init__(parent)
        self._monitor = monitor
        self.setWindowTitle("Activity monitoring privacy")
        self.resize(480, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Enter one process filename or window-title phrase per line. "
                "These exclusions remain local in Windows app settings. Known "
                "private messaging and AI chat apps are always excluded."
            )
        )
        layout.addWidget(QLabel("Excluded processes (for example: browser.exe):"))
        self.processes_edit = QPlainTextEdit()
        self.processes_edit.setPlainText(
            "\n".join(
                sorted(
                    monitor.excluded_process_names
                    - set(DEFAULT_EXCLUDED_PROCESS_NAMES)
                )
            )
        )
        layout.addWidget(self.processes_edit)
        layout.addWidget(
            QLabel(
                "Excluded window-title phrases (sensitive financial, health, "
                "password, and private/incognito titles are always skipped):"
            )
        )
        self.titles_edit = QPlainTextEdit()
        self.titles_edit.setPlainText(
            "\n".join(sorted(monitor.excluded_title_terms))
        )
        layout.addWidget(self.titles_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        self._monitor.set_exclusions(
            self._lines(self.processes_edit.toPlainText()),
            self._lines(self.titles_edit.toPlainText()),
        )
        super().accept()

    @staticmethod
    def _lines(text: str) -> list[str]:
        return [line.strip() for line in text.splitlines() if line.strip()]
