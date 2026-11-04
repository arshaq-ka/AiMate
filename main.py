import logging
import sys
from pathlib import Path

from PySide6.QtCore import QLockFile, QPoint, QStandardPaths
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

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
        writing_assistant.processing_changed.connect(character.set_thinking)
        character.writing_assistant_requested.connect(
            writing_assistant.show_and_focus
        )
        tray = SystemTrayController(app, character, writing_assistant.show_and_focus)
        character.quit_requested.connect(tray.quit_application)
        tray.quit_requested.connect(app.quit)
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