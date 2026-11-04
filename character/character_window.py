import math

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QMenu, QWidget

from character.animations import CharacterAnimation
from character.states import CharacterState


class CharacterWindow(QWidget):
    animation_paused_changed = Signal(bool)
    quit_requested = Signal()
    writing_assistant_requested = Signal()

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowTitle("Local AI Desktop Companion")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(190, 220)
        self.setMouseTracking(True)

        self.animation = CharacterAnimation(self)
        self.animation.frame_updated.connect(self.update)
        self.animation.paused_changed.connect(self.animation_paused_changed)
        self.animation.start()
        self._drag_offset: QPoint | None = None
        self._thinking = False
        self._place_near_screen_corner()

    @property
    def state(self) -> CharacterState:
        if self.animation.is_paused:
            return CharacterState.PAUSED
        return CharacterState.THINKING if self._thinking else CharacterState.IDLE

    def _place_near_screen_corner(self) -> None:
        screen = self.screen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(area.right() - self.width() - 24, area.bottom() - self.height() - 36)

    def pause_animation(self) -> None:
        self.animation.pause()
        self.update()

    def resume_animation(self) -> None:
        self.animation.start()

    def toggle_animation(self) -> None:
        self.animation.toggle()
        self.update()

    def stop_animation(self) -> None:
        self.animation.stop()

    def set_thinking(self, thinking: bool) -> None:
        self._thinking = thinking
        self.update()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt event override
        event.ignore()
        self.hide()

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt event override
        menu = QMenu(self)
        pause_action = QAction(
            "Resume animation" if self.animation.is_paused else "Pause animation",
            menu,
        )
        pause_action.triggered.connect(self.toggle_animation)
        writing_action = QAction("Open writing assistant", menu)
        writing_action.triggered.connect(self.writing_assistant_requested)
        hide_action = QAction("Hide character", menu)
        hide_action.triggered.connect(self.hide)
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quit_requested)
        menu.addAction(pause_action)
        menu.addAction(writing_action)
        menu.addAction(hide_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        menu.exec(event.globalPos())

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt event override
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt event override
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt event override
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt event override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        float_y = math.sin(self.animation.phase) * 4.0
        painter.translate(0, float_y)
        self._draw_glow(painter)
        self._draw_robot(painter)
        painter.end()

    def _draw_glow(self, painter: QPainter) -> None:
        glow = QRadialGradient(QPointF(95, 106), 88)
        glow.setColorAt(0.0, QColor(111, 143, 255, 58))
        glow.setColorAt(0.58, QColor(119, 105, 250, 22))
        glow.setColorAt(1.0, QColor(119, 105, 250, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QRectF(8, 18, 174, 174))

    def _draw_robot(self, painter: QPainter) -> None:
        painter.setPen(Qt.PenStyle.NoPen)

        # Soft ground shadow
        shadow = QRadialGradient(QPointF(95, 194), 49)
        shadow.setColorAt(0.0, QColor(49, 56, 110, 82))
        shadow.setColorAt(1.0, QColor(49, 56, 110, 0))
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(QRectF(43, 178, 104, 31))

        # Antenna and side pieces
        painter.setPen(QPen(QColor("#91a3ff"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(95, 39), QPointF(95, 28))
        painter.setPen(Qt.PenStyle.NoPen)
        antenna = QRadialGradient(QPointF(95, 25), 9)
        antenna.setColorAt(0, QColor("#e6f4ff"))
        antenna.setColorAt(0.48, QColor("#72d5ff"))
        antenna.setColorAt(1, QColor("#7668f2"))
        painter.setBrush(QBrush(antenna))
        painter.drawEllipse(QRectF(87, 17, 16, 16))

        painter.setBrush(QColor("#8190ec"))
        painter.drawRoundedRect(QRectF(26, 78, 20, 34), 9, 9)
        painter.drawRoundedRect(QRectF(144, 78, 20, 34), 9, 9)
        painter.setBrush(QColor("#b9c9ff"))
        painter.drawRoundedRect(QRectF(31, 84, 9, 22), 4, 4)
        painter.drawRoundedRect(QRectF(150, 84, 9, 22), 4, 4)

        # Compact body and arms
        body_gradient = QLinearGradient(51, 135, 139, 184)
        body_gradient.setColorAt(0, QColor("#f9fcff"))
        body_gradient.setColorAt(0.48, QColor("#dce8ff"))
        body_gradient.setColorAt(1, QColor("#aebaff"))
        painter.setBrush(QBrush(body_gradient))
        painter.drawRoundedRect(QRectF(56, 137, 78, 50), 22, 22)
        painter.setBrush(QColor("#dce5ff"))
        painter.drawRoundedRect(QRectF(44, 145, 19, 30), 9, 9)
        painter.drawRoundedRect(QRectF(127, 145, 19, 30), 9, 9)
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(QRectF(76, 148, 38, 25), 12, 12)
        painter.setBrush(QColor("#776cf2"))
        painter.drawEllipse(QRectF(87, 155, 16, 11))
        painter.setBrush(QColor("#b5f2ff"))
        painter.drawEllipse(QRectF(92, 158, 6, 5))

        # Face shell
        face_gradient = QLinearGradient(44, 45, 136, 132)
        face_gradient.setColorAt(0, QColor("#ffffff"))
        face_gradient.setColorAt(0.42, QColor("#f0f5ff"))
        face_gradient.setColorAt(1, QColor("#cbd5ff"))
        painter.setBrush(QBrush(face_gradient))
        painter.setPen(QPen(QColor(119, 132, 224, 120), 1.4))
        painter.drawRoundedRect(QRectF(38, 39, 114, 96), 34, 34)
        painter.setPen(Qt.PenStyle.NoPen)

        # Face screen
        screen_gradient = QLinearGradient(49, 51, 141, 122)
        screen_gradient.setColorAt(0, QColor("#26336d"))
        screen_gradient.setColorAt(1, QColor("#403d91"))
        painter.setBrush(QBrush(screen_gradient))
        painter.drawRoundedRect(QRectF(48, 52, 94, 70), 26, 26)

        eye_height = 3.0 if not self.animation.eyes_open else 16.0
        painter.setBrush(QColor("#8ce7ff"))
        painter.drawEllipse(QRectF(69, 75 + (16 - eye_height) / 2, 13, eye_height))
        painter.drawEllipse(QRectF(108, 75 + (16 - eye_height) / 2, 13, eye_height))
        painter.setBrush(QColor(255, 255, 255, 190))
        painter.drawEllipse(QRectF(72, 77, 4, 4))
        painter.drawEllipse(QRectF(111, 77, 4, 4))

        smile = QPainterPath()
        smile.moveTo(87, 101)
        smile.quadTo(95, 107, 103, 101)
        painter.setPen(QPen(QColor("#a8a4ff"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawPath(smile)

        # Status light and label
        status_color = {
            CharacterState.IDLE: QColor("#74e6bd"),
            CharacterState.THINKING: QColor("#a18bff"),
            CharacterState.PAUSED: QColor("#ffcf70"),
        }[self.state]
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(status_color)
        painter.drawEllipse(QRectF(51, 193, 7, 7))
        painter.setPen(QColor("#53618f"))
        font = painter.font()
        font.setPointSize(7)
        painter.setFont(font)
        painter.drawText(
            QRectF(61, 188, 78, 18),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.state.value.upper(),
        )
