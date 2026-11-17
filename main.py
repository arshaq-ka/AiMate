import logging
import sys
from pathlib import Path

from PySide6.QtCore import QLockFile, QPoint, QStandardPaths
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from activity_monitor.activity_history import ActivityHistoryWindow
from activity_monitor.app_tracker import ActivityMonitor
from activity_monitor.privacy_settings import PrivacySettingsDialog
from character.character_window import CharacterWindow
from character.tray import SystemTrayController
from text_assistant.selection import (
    SelectionController,
    cursor_position,
    foreground_window_handle,
)
from text_assistant.shortcuts import GlobalShortcut, ShortcutUnavailableError
from text_assistant.writing_window import WritingAssistantWindow


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Local AI Desktop Companion")
    app.setQuitOnLastWindowClosed(False)

    data_directory = Path(
        QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppLocalDataLocation
        )
    )
    data_directory.mkdir(parents=True, exist_ok=True)
    instance_lock = QLockFile(str(data_directory / "companion.lock"))
    if not instance_lock.tryLock(0):
        QMessageBox.information(
            None,
            "Companion already running",
            "The desktop companion is already running. Use its system-tray "
            "icon to show it or quit it.",
        )
        return 0

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None,
            "System tray unavailable",
            "The Windows system tray is unavailable. The companion cannot run "
            "safely because its hide and quit controls would be inaccessible.",
        )
        return 1

    shortcut = None
    shortcut_error = None
    try:
        character = CharacterWindow()
        writing_assistant = WritingAssistantWindow()
        activity_monitor = ActivityMonitor(app)
        activity_history = ActivityHistoryWindow(activity_monitor)
        writing_assistant.processing_changed.connect(character.set_thinking)
        activity_monitor.state_changed.connect(character.set_monitoring)
        character.writing_assistant_requested.connect(
            writing_assistant.show_and_focus
        )

        def update_monitoring_menu(_active: bool = False) -> None:
            tray.set_monitoring_state(
                activity_monitor.monitoring,
                activity_monitor.paused,
                activity_monitor.screenshots_enabled,
            )

        def toggle_activity_monitoring() -> None:
            if activity_monitor.monitoring and not activity_monitor.paused:
                activity_monitor.pause()
                return
            if activity_monitor.monitoring and activity_monitor.paused:
                activity_monitor.resume()
                return
            answer = QMessageBox.question(
                None,
                "Start activity monitoring?",
                "The companion will record the active application's process name, "
                "window title, category, and time spent, while keeping records in "
                "memory for this run only. It does not record keystrokes or read "
                "document contents. Sensitive/password/private windows are "
                "automatically skipped. Start monitoring?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                activity_monitor.start()

        def open_activity_privacy() -> None:
            dialog = PrivacySettingsDialog(activity_monitor)
            dialog.exec()

        def toggle_screenshot_capture() -> None:
            if activity_monitor.screenshots_enabled:
                activity_monitor.disable_screenshot_capture()
                update_monitoring_menu()
                tray.show_notification(
                    "Screenshots disabled",
                    "Periodic screenshots and OCR have been disabled.",
                )
                return
            if not activity_monitor.monitoring:
                tray.show_notification(
                    "Start monitoring first",
                    "Enable activity monitoring before optional screenshots.",
                )
                return
            answer = QMessageBox.warning(
                None,
                "Enable screenshots and OCR?",
                "With your separate consent, the companion will capture only the "
                "active window every five minutes and run local OCR. Screenshots "
                "and OCR text remain in memory only; the most recent capture can "
                "be reviewed and is never uploaded. Password, private, excluded, "
                "and sensitive windows are skipped. Enable this optional feature?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                activity_monitor.enable_screenshot_capture()
            except (OSError, RuntimeError) as exc:
                tray.show_notification("Screenshots unavailable", str(exc))
                return
            update_monitoring_menu()

        tray = SystemTrayController(
            app,
            character,
            writing_assistant.show_and_focus,
            toggle_activity_monitoring,
            activity_history.show,
            open_activity_privacy,
            toggle_screenshot_capture,
        )
        character.quit_requested.connect(tray.quit_application)
        character.activity_monitor_requested.connect(toggle_activity_monitoring)
        character.activity_history_requested.connect(activity_history.show)
        character.activity_privacy_requested.connect(open_activity_privacy)
        character.screenshot_capture_requested.connect(toggle_screenshot_capture)
        tray.quit_requested.connect(app.quit)
        activity_monitor.state_changed.connect(
            lambda _monitoring, _paused: update_monitoring_menu()
        )
        update_monitoring_menu()
        activity_monitor.privacy_skip.connect(
            lambda message: tray.show_notification("Privacy protection", message)
        )
        activity_monitor.monitoring_error.connect(
            lambda message: tray.show_notification("Monitoring error", message)
        )
        activity_monitor.screenshot_ready.connect(activity_history.refresh)
        selection_controller = SelectionController(app)
        selection_controller.selection_ready.connect(
            writing_assistant.present_selection_and_suggest
        )
        selection_controller.selection_failed.connect(
            writing_assistant.show_selection_error
        )

        def capture_selection() -> None:
            try:
                target_window = foreground_window_handle()
                anchor = cursor_position()
            except OSError as exc:
                writing_assistant.show_selection_error(str(exc), 0, QPoint())
                return

            if not target_window:
                writing_assistant.show_selection_error(
                    "Windows could not identify the active application window.",
                    0,
                    anchor,
                )
                return
            selection_controller.capture(target_window, anchor)

        try:
            shortcut = GlobalShortcut(capture_selection)
            app.installNativeEventFilter(shortcut)
        except ShortcutUnavailableError as exc:
            shortcut_error = str(exc)
            logging.getLogger(__name__).warning(
                "Global selection shortcut is unavailable: %s", exc
            )
    except Exception:
        logging.exception("Could not start the desktop companion")
        QMessageBox.critical(
            None,
            "Startup failed",
            "The desktop companion could not start. See the console output "
            "for details.",
        )
        return 1

    app.aboutToQuit.connect(character.stop_animation)
    app.aboutToQuit.connect(writing_assistant.shutdown)
    app.aboutToQuit.connect(selection_controller.shutdown)
    app.aboutToQuit.connect(activity_monitor.shutdown)
    app.aboutToQuit.connect(instance_lock.unlock)
    if shortcut is not None:
        app.aboutToQuit.connect(shortcut.unregister)
        app.aboutToQuit.connect(lambda: app.removeNativeEventFilter(shortcut))
    tray.show()
    if shortcut_error:
        tray.show_notification("Shortcut unavailable", shortcut_error)
    character.show()
    character.raise_()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
#phase 3 completed