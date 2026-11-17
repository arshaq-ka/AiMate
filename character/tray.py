from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from character.character_window import CharacterWindow


class SystemTrayController(QObject):
    quit_requested = Signal()

    def __init__(
        self,
        app: QApplication,
        character: CharacterWindow,
        show_writing_assistant: Callable[[], None],
        activity_action: Callable[[], None] | None = None,
        show_activity_history: Callable[[], None] | None = None,
        edit_activity_privacy: Callable[[], None] | None = None,
        toggle_screenshot_capture: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(app)
        self._app = app
        self._character = character
        self._icon = QSystemTrayIcon(self)
        self._icon.setIcon(self._create_icon())
        self._icon.setToolTip("Local AI Desktop Companion")

        self._menu = QMenu()
        self._show_action = QAction("Show character", self._menu)
        self._hide_action = QAction("Hide character", self._menu)
        writing_action = QAction("Open writing assistant", self._menu)
        self._animation_action = QAction("Pause animation", self._menu)
        self._quit_action = QAction("Quit", self._menu)
        self._monitoring_action = None
        self._history_action = None
        self._privacy_action = None
        self._screenshot_action = None

        self._show_action.triggered.connect(self.show_character)
        self._hide_action.triggered.connect(self._character.hide)
        writing_action.triggered.connect(show_writing_assistant)
        self._animation_action.triggered.connect(self._character.toggle_animation)
        self._quit_action.triggered.connect(self.quit_application)
        self._menu.addAction(self._show_action)
        self._menu.addAction(self._hide_action)
        self._menu.addAction(writing_action)
        self._menu.addSeparator()
        self._menu.addAction(self._animation_action)
        if activity_action and show_activity_history and edit_activity_privacy:
            self._menu.addSeparator()
            self._monitoring_action = QAction("Start activity monitoring", self._menu)
            self._history_action = QAction("View activity history", self._menu)
            self._privacy_action = QAction("Activity privacy exclusions", self._menu)
            self._monitoring_action.triggered.connect(activity_action)
            self._history_action.triggered.connect(show_activity_history)
            self._privacy_action.triggered.connect(edit_activity_privacy)
            self._menu.addAction(self._monitoring_action)
            self._menu.addAction(self._history_action)
            self._menu.addAction(self._privacy_action)
            if toggle_screenshot_capture:
                self._screenshot_action = QAction(
                    "Enable periodic screenshots and OCR",
                    self._menu,
                )
                self._screenshot_action.triggered.connect(
                    toggle_screenshot_capture
                )
                self._menu.addAction(self._screenshot_action)
        self._menu.addSeparator()
        self._menu.addAction(self._quit_action)
        self._icon.setContextMenu(self._menu)
        self._icon.activated.connect(self._on_activated)
        self._character.animation_paused_changed.connect(self._update_animation_action)

    def show(self) -> None:
        self._icon.show()

    def show_notification(self, title: str, message: str) -> None:
        self._icon.showMessage(
            title,
            message,
            QSystemTrayIcon.MessageIcon.Warning,
            8000,
        )

    def set_monitoring_state(
        self,
        monitoring: bool,
        paused: bool = False,
        screenshots_enabled: bool = False,
    ) -> None:
        if self._monitoring_action is not None:
            if not monitoring:
                self._monitoring_action.setText("Start activity monitoring")
            elif paused:
                self._monitoring_action.setText("Resume activity monitoring")
            else:
                self._monitoring_action.setText("Pause activity monitoring")
        if self._screenshot_action is not None:
            self._screenshot_action.setText(
                "Disable periodic screenshots and OCR"
                if screenshots_enabled
                else "Enable periodic screenshots and OCR"
            )
        state = (
            "paused"
            if paused
            else "on"
            if monitoring
            else "off"
        )
        self._icon.setToolTip(
            f"Local AI Desktop Companion • Monitoring {state}"
        )
        self._icon.setIcon(self._create_icon(monitoring, paused))

    def quit_application(self) -> None:
        self._icon.hide()
        self._character.hide()
        self.quit_requested.emit()
        self._app.exit(0)

    def show_character(self) -> None:
        self._character.show()
        self._character.raise_()
        self._character.activateWindow()

    def _update_animation_action(self, paused: bool) -> None:
        self._animation_action.setText(
            "Resume animation" if paused else "Pause animation"
        )

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            if self._character.isVisible():
                self._character.hide()
            else:
                self.show_character()

    @staticmethod
    def _create_icon(monitoring: bool = False, paused: bool = False) -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#7069e8"))
        painter.drawRoundedRect(6, 7, 52, 50, 20, 20)
        painter.setBrush(QColor("#27336d"))
        painter.drawRoundedRect(13, 17, 38, 29, 12, 12)
        painter.setBrush(QColor("#8ce7ff"))
        painter.drawEllipse(21, 25, 6, 9)
        painter.drawEllipse(37, 25, 6, 9)
        if monitoring:
            painter.setBrush(QColor("#ffcf70") if paused else QColor("#35c879"))
            painter.setPen(QColor("#ffffff"))
            painter.drawEllipse(43, 42, 13, 13)
        painter.end()
        return QIcon(pixmap)
