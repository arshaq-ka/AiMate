from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
)

from activity_monitor.app_tracker import ActivityMonitor, ActivityRecord


class ActivityHistoryWindow(QDialog):
    def __init__(self, monitor: ActivityMonitor, parent=None) -> None:
        super().__init__(parent)
        self._monitor = monitor
        self.setWindowTitle("Local activity review")
        self.resize(760, 560)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "In-memory activity only. This Phase 4 build does not save activity "
                "or screenshots to disk. Review and delete entries here."
            )
        )
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )
        self.list_widget.currentItemChanged.connect(self._show_details)
        layout.addWidget(self.list_widget, 2)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(120)
        layout.addWidget(self.details)
        self.screenshot_label = QLabel("No screenshot captured.")
        self.screenshot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screenshot_label.setMinimumHeight(100)
        self.screenshot_label.setMaximumHeight(220)
        layout.addWidget(self.screenshot_label)

        controls = QHBoxLayout()
        note_button = QPushButton("Add note")
        note_button.clicked.connect(self._add_note)
        delete_button = QPushButton("Delete selected")
        delete_button.clicked.connect(self._delete_selected)
        clear_button = QPushButton("Delete all activity")
        clear_button.clicked.connect(self._clear_all)
        controls.addWidget(note_button)
        controls.addWidget(delete_button)
        controls.addWidget(clear_button)
        layout.addLayout(controls)

        self._monitor.records_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        selected_ids = {
            str(item.data(Qt.ItemDataRole.UserRole))
            for item in self.list_widget.selectedItems()
        }
        self.list_widget.clear()
        for record in reversed(self._monitor.records):
            item = QListWidgetItem(self._format_record(record))
            item.setData(Qt.ItemDataRole.UserRole, record.record_id)
            self.list_widget.addItem(item)
            if record.record_id in selected_ids:
                item.setSelected(True)
        screenshot = self._monitor.latest_screenshot
        if screenshot:
            image = screenshot["image"]
            rgb_image = image.convert("RGB")
            qimage = QImage(
                rgb_image.tobytes(),
                rgb_image.width,
                rgb_image.height,
                rgb_image.width * 3,
                QImage.Format.Format_RGB888,
            ).copy()
            self.screenshot_label.setPixmap(
                QPixmap.fromImage(qimage).scaled(
                    self.screenshot_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.screenshot_label.setPixmap(QPixmap())
            self.screenshot_label.setText("No screenshot captured.")

    @staticmethod
    def _format_record(record: ActivityRecord) -> str:
        start = record.start_time.strftime("%H:%M:%S")
        if record.is_note:
            return f"{start}  NOTE  {record.description}"
        minutes, seconds = divmod(record.duration_seconds, 60)
        return (
            f"{start}  {record.category}  {record.application_name}  "
            f"({minutes}m {seconds}s)"
        )

    def _show_details(self, item, previous=None) -> None:
        del previous
        if item is None:
            self.details.clear()
            return
        record_id = str(item.data(Qt.ItemDataRole.UserRole))
        record = next(
            (
                record
                for record in self._monitor.records
                if record.record_id == record_id
            ),
            None,
        )
        if record is None:
            self.details.clear()
            return
        details = [
            f"Application: {record.application_name}",
            f"Window: {record.window_title}",
            f"Category: {record.category}",
            f"Start: {record.start_time.isoformat(timespec='seconds')}",
            f"End: {record.end_time.isoformat(timespec='seconds')}",
        ]
        if record.description:
            details.append(f"Description: {record.description}")
        if self._monitor.latest_screenshot:
            screenshot = self._monitor.latest_screenshot
            captured_at: datetime = screenshot["captured_at"]
            details.extend(
                [
                    "",
                    f"Latest OCR capture: {captured_at.isoformat(timespec='seconds')}",
                    screenshot["recognized_text"] or "(No text recognized.)",
                ]
            )
        self.details.setPlainText("\n".join(details))

    def _add_note(self) -> None:
        note, accepted = QInputDialog.getMultiLineText(
            self,
            "Add activity note",
            "Write a note to keep in this session's local activity review:",
        )
        if accepted and note.strip():
            self._monitor.add_note(note)

    def _delete_selected(self) -> None:
        selected_ids = {
            str(item.data(Qt.ItemDataRole.UserRole))
            for item in self.list_widget.selectedItems()
        }
        if selected_ids:
            self._monitor.delete_records(selected_ids)

    def _clear_all(self) -> None:
        if QMessageBox.question(
            self,
            "Delete all activity?",
            "Delete every activity record and manual note currently held in memory?",
        ) == QMessageBox.StandardButton.Yes:
            self._monitor.clear_records()
