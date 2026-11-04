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
    def _create_icon() -> QIcon:
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
        painter.end()
        return QIcon(pixmap)
