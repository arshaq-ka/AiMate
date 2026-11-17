import ctypes
import sys
from ctypes import wintypes

from PIL import Image, ImageGrab
from PySide6.QtCore import QObject, Signal

from activity_monitor.ocr import extract_text
from activity_monitor.privacy import (
    check_window_privacy,
    focused_control_is_password,
)
from activity_monitor.window_tracker import ActiveWindow, get_active_window


def capture_window(window_handle: int) -> Image.Image:
    if sys.platform != "win32":
        raise OSError("Screen capture is available only on Windows.")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.RECT),
    ]
    user32.GetWindowRect.restype = wintypes.BOOL
    if int(user32.GetForegroundWindow() or 0) != window_handle:
        raise PermissionError(
            "The active application changed; no screenshot was taken."
        )
    rectangle = wintypes.RECT()
    if not user32.GetWindowRect(window_handle, ctypes.byref(rectangle)):
        raise ctypes.WinError(ctypes.get_last_error())
    if rectangle.right <= rectangle.left or rectangle.bottom <= rectangle.top:
        raise OSError("The active window has no capturable screen area.")

    image = ImageGrab.grab(
        bbox=(
            rectangle.left,
            rectangle.top,
            rectangle.right,
            rectangle.bottom,
        ),
        all_screens=True,
    )
    if image.width < 2 or image.height < 2:
        raise OSError("Windows returned an empty screenshot.")
    if int(user32.GetForegroundWindow() or 0) != window_handle:
        raise PermissionError(
            "The active application changed during capture; the screenshot "
            "was discarded."
        )
    return image


class ScreenCaptureWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)
    privacy_skipped = Signal(str)
    finished = Signal()

    def __init__(
        self,
        excluded_process_names: set[str],
        excluded_title_terms: set[str],
    ) -> None:
        super().__init__()
        self._excluded_process_names = excluded_process_names
        self._excluded_title_terms = excluded_title_terms

    def run(self) -> None:
        try:
            window = get_active_window()
            if window is None:
                raise OSError("No active application window was found.")
            decision = check_window_privacy(
                window,
                self._excluded_process_names,
                self._excluded_title_terms,
            )
            if not decision.allowed:
                raise PermissionError(
                    f"Screenshot skipped because this is a {decision.reason}."
                )
            if focused_control_is_password(window.handle):
                raise PermissionError(
                    "Screenshot skipped because the focused control is a "
                    "password field."
                )
            current = get_active_window()
            if current is None or current.handle != window.handle:
                raise PermissionError(
                    "The active application changed; no screenshot was taken."
                )
            image = capture_window(window.handle)
            if focused_control_is_password(window.handle):
                raise PermissionError(
                    "Screenshot discarded because the focused control is a "
                    "password field."
                )
            text = extract_text(image)
            self.completed.emit(
                {
                    "active_window": window,
                    "image": image,
                    "recognized_text": text,
                }
            )
        except PermissionError as exc:
            self.privacy_skipped.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()
