import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QObject, QSettings, QThread, QTimer, Signal

from activity_monitor.activity_classifier import classify_activity
from activity_monitor.privacy import (
    DEFAULT_EXCLUDED_PROCESS_NAMES,
    check_window_privacy,
)
from activity_monitor.window_tracker import ActiveWindow, get_active_window

logger = logging.getLogger(__name__)

POLL_INTERVAL_MS = 3000


@dataclass
class ActivityRecord:
    record_id: str
    start_time: datetime
    end_time: datetime
    application_name: str
    window_title: str
    category: str
    description: str
    is_note: bool = False

    @property
    def duration_seconds(self) -> int:
        return max(0, int((self.end_time - self.start_time).total_seconds()))


class ActivityMonitor(QObject):
    state_changed = Signal(bool, bool)
    records_changed = Signal()
    privacy_skip = Signal(str)
    monitoring_error = Signal(str)
    screenshot_ready = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.settings = QSettings("AiMate", "DesktopCompanion")
        self.records: list[ActivityRecord] = []
        self.monitoring = False
        self.paused = False
        self._screenshots_enabled = False
        self._active_record: ActivityRecord | None = None
        self._last_privacy_reason = ""
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        self._screenshot_timer = QTimer(self)
        self._screenshot_timer.setInterval(5 * 60 * 1000)
        self._screenshot_timer.timeout.connect(self.capture_screenshot)
        self.latest_screenshot = None
        self._capture_thread = None
        self._capture_worker = None

    @property
    def excluded_process_names(self) -> set[str]:
        configured = self.settings.value("activity/excludedProcesses", [])
        if isinstance(configured, str):
            configured = [line.strip() for line in configured.splitlines()]
        return {
            str(name).strip().casefold()
            for name in configured or []
            if str(name).strip()
        } | set(DEFAULT_EXCLUDED_PROCESS_NAMES)

    @property
    def excluded_title_terms(self) -> set[str]:
        configured = self.settings.value("activity/excludedTitleTerms", [])
        if isinstance(configured, str):
            configured = [line.strip() for line in configured.splitlines()]
        return {
            str(term).strip().casefold()
            for term in configured or []
            if str(term).strip()
        }

    def start(self) -> None:
        if self.monitoring and not self.paused:
            return
        self.monitoring = True
        self.paused = False
        self._timer.start()
        if self._screenshots_enabled:
            self._screenshot_timer.start()
        self.state_changed.emit(True, False)
        self._poll()

    def pause(self) -> None:
        if not self.monitoring or self.paused:
            return
        self.paused = True
        self._timer.stop()
        self._screenshot_timer.stop()
        self._close_active_record()
        self.state_changed.emit(True, True)

    def resume(self) -> None:
        if not self.monitoring or not self.paused:
            return
        self.paused = False
        self._timer.start()
        if self._screenshots_enabled:
            self._screenshot_timer.start()
        self.state_changed.emit(True, False)
        self._poll()

    def stop(self) -> None:
        if not self.monitoring:
            return
        self.monitoring = False
        self.paused = False
        self._timer.stop()
        self._screenshot_timer.stop()
        self._screenshots_enabled = False
        self.latest_screenshot = None
        self._close_active_record()
        self.state_changed.emit(False, False)

    def toggle_pause(self) -> None:
        if self.paused:
            self.resume()
        else:
            self.pause()

    def set_exclusions(
        self,
        process_names: list[str],
        title_terms: list[str],
    ) -> None:
        self.settings.setValue(
            "activity/excludedProcesses",
            sorted(
                {
                    name.strip().casefold()
                    for name in process_names
                    if name.strip()
                }
            ),
        )
        self.settings.setValue(
            "activity/excludedTitleTerms",
            sorted(
                {
                    term.strip().casefold()
                    for term in title_terms
                    if term.strip()
                }
            ),
        )
        self._close_active_record()

    def add_note(self, note: str) -> None:
        description = note.strip()
        if not description:
            raise ValueError("Activity note cannot be empty.")
        now = datetime.now().astimezone()
        self.records.append(
            ActivityRecord(
                record_id=str(uuid.uuid4()),
                start_time=now,
                end_time=now,
                application_name="Manual note",
                window_title="User-added note",
                category="Other",
                description=description,
                is_note=True,
            )
        )
        self.records_changed.emit()

    def delete_records(self, record_ids: set[str]) -> None:
        self.records = [
            record for record in self.records if record.record_id not in record_ids
        ]
        if (
            self._active_record is not None
            and self._active_record.record_id in record_ids
        ):
            self._active_record = None
        self.records_changed.emit()

    def clear_records(self) -> None:
        self.records.clear()
        self._active_record = None
        self.records_changed.emit()

    def enable_screenshot_capture(self) -> None:
        if not self.monitoring:
            raise RuntimeError("Start activity monitoring before screen capture.")
        try:
            import pytesseract  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "Install the optional pytesseract package before enabling OCR."
            ) from exc
        import shutil
        import pytesseract

        if not pytesseract.pytesseract.tesseract_cmd:
            raise RuntimeError("Tesseract OCR executable is not configured.")
        if (
            pytesseract.pytesseract.tesseract_cmd == "tesseract"
            and shutil.which("tesseract") is None
        ):
            raise RuntimeError(
                "Tesseract OCR was not found. Install Tesseract locally, then "
                "restart the app before enabling screenshots."
            )
        try:
            pytesseract.get_tesseract_version()
        except (pytesseract.TesseractNotFoundError, RuntimeError) as exc:
            raise RuntimeError(
                "Tesseract OCR is not installed or could not start. Install it "
                "locally before enabling screenshots."
            ) from exc
        self._screenshots_enabled = True
        if not self.paused:
            self._screenshot_timer.start()
        self.capture_screenshot()

    def disable_screenshot_capture(self) -> None:
        self._screenshots_enabled = False
        self._screenshot_timer.stop()
        self.latest_screenshot = None

    @property
    def screenshots_enabled(self) -> bool:
        return self._screenshots_enabled

    def capture_screenshot(self) -> None:
        if (
            not self.monitoring
            or self.paused
            or not self._screenshots_enabled
            or self._capture_thread is not None
        ):
            return
        from activity_monitor.screen_capture import ScreenCaptureWorker

        thread = QThread(self)
        worker = ScreenCaptureWorker(
            self.excluded_process_names,
            self.excluded_title_terms,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._on_screenshot_completed)
        worker.failed.connect(self.monitoring_error)
        worker.privacy_skipped.connect(self.privacy_skip)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_screenshot_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._capture_thread = thread
        self._capture_worker = worker
        thread.start()

    def _on_screenshot_completed(self, result: dict) -> None:
        if (
            not self.monitoring
            or self.paused
            or not self._screenshots_enabled
        ):
            return
        window: ActiveWindow = result["active_window"]
        decision = check_window_privacy(
            window,
            self.excluded_process_names,
            self.excluded_title_terms,
        )
        if not decision.allowed:
            self.privacy_skip.emit(
                f"Screenshot skipped because this is a {decision.reason}."
            )
            return
        self.latest_screenshot = {
            "captured_at": datetime.now().astimezone(),
            "application_name": window.process_name,
            "window_title": window.title,
            "image": result["image"],
            "recognized_text": result["recognized_text"],
        }
        self.records_changed.emit()
        self.screenshot_ready.emit()

    def _on_screenshot_thread_finished(self) -> None:
        self._capture_thread = None
        self._capture_worker = None

    def _poll(self) -> None:
        if not self.monitoring or self.paused:
            return
        try:
            window = get_active_window()
        except OSError as exc:
            self.monitoring_error.emit(str(exc))
            self.pause()
            return
        if window is None:
            self._close_active_record()
            return

        decision = check_window_privacy(
            window,
            self.excluded_process_names,
            self.excluded_title_terms,
        )
        if not decision.allowed:
            self._close_active_record()
            if decision.reason != self._last_privacy_reason:
                self.privacy_skip.emit(
                    f"Window skipped: {decision.reason}. Activity continues "
                    "for other windows."
                )
            self._last_privacy_reason = decision.reason
            return
        self._last_privacy_reason = ""

        now = datetime.now().astimezone()
        if self._same_window(self._active_record, window):
            self._active_record.end_time = now
            self.records_changed.emit()
            return

        self._close_active_record()
        record = ActivityRecord(
            record_id=str(uuid.uuid4()),
            start_time=now,
            end_time=now,
            application_name=window.process_name,
            window_title=window.title,
            category=classify_activity(window),
            description="Active window",
        )
        self.records.append(record)
        self._active_record = record
        self.records_changed.emit()

    @staticmethod
    def _same_window(
        record: ActivityRecord | None,
        window: ActiveWindow,
    ) -> bool:
        return bool(
            record
            and not record.is_note
            and record.application_name == window.process_name
            and record.window_title == window.title
        )

    def _close_active_record(self) -> None:
        if self._active_record is not None:
            self._active_record.end_time = max(
                self._active_record.end_time,
                datetime.now().astimezone(),
            )
            self._active_record = None
            self.records_changed.emit()

    def shutdown(self) -> None:
        self.stop()
        thread = self._capture_thread
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait()
