import random

from PySide6.QtCore import QObject, QTimer, Signal


class CharacterAnimation(QObject):
    frame_updated = Signal()
    paused_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.phase = 0.0
        self._frames_until_blink = 75
        self._blink_frames_remaining = 0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self.advance_frame)

    @property
    def is_paused(self) -> bool:
        return not self._timer.isActive()

    @property
    def eyes_open(self) -> bool:
        return self._blink_frames_remaining == 0

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
            self.paused_changed.emit(False)

    def pause(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self.paused_changed.emit(True)

    def toggle(self) -> None:
        if self.is_paused:
            self.start()
        else:
            self.pause()

    def stop(self) -> None:
        self._timer.stop()

    def advance_frame(self) -> None:
        if self.is_paused:
            return

        self.phase = (self.phase + 0.045) % (2 * 3.141592653589793)
        if self._blink_frames_remaining:
            self._blink_frames_remaining -= 1
        else:
            self._frames_until_blink -= 1
            if self._frames_until_blink <= 0:
                self._blink_frames_remaining = 4
                self._frames_until_blink = random.randint(75, 145)
        self.frame_updated.emit()
