import ctypes
import logging
import sys
from ctypes import wintypes

from PySide6.QtCore import QObject, QPoint, QThread, Signal

logger = logging.getLogger(__name__)

MAX_SELECTION_LENGTH = 12000


class SelectionUnavailableError(RuntimeError):
    """Raised when the focused Windows control does not expose selected text."""


class WindowsSelectionReader:
    """Read selected text from the focused control via Windows UI Automation."""

    def read_selection(self, target_window: int) -> str:
        if sys.platform != "win32":
            raise SelectionUnavailableError(
                "Text selection detection is available only on Windows."
            )

        from comtypes import COMError, CoInitialize, CoUninitialize
        from comtypes.client import CreateObject, GetModule

        initialized = False
        try:
            if foreground_window_handle() != target_window:
                raise SelectionUnavailableError(
                    "The active application changed before its selection could be "
                    "read. Select the text again and retry."
                )
            CoInitialize()
            initialized = True
            GetModule("UIAutomationCore.dll")
            from comtypes.gen.UIAutomationClient import (
                CUIAutomation,
                IUIAutomation,
                IUIAutomationTextPattern,
                UIA_TextPatternId,
            )

            automation = CreateObject(CUIAutomation, interface=IUIAutomation)
            if foreground_window_handle() != target_window:
                raise SelectionUnavailableError(
                    "The active application changed before its selection could be "
                    "read. Select the text again and retry."
                )
            element = automation.GetFocusedElement()
            if element is None:
                raise SelectionUnavailableError(
                    "Windows UI Automation could not find the focused control."
                )

            pattern = element.GetCurrentPattern(UIA_TextPatternId)
            if pattern is None:
                raise SelectionUnavailableError(
                    "This control does not expose selected text through Windows "
                    "UI Automation. You can paste the copied text into the "
                    "assistant instead."
                )

            try:
                text_pattern = pattern.QueryInterface(IUIAutomationTextPattern)
            except (COMError, ValueError) as exc:
                raise SelectionUnavailableError(
                    "This control does not expose selected text through Windows "
                    "UI Automation. You can paste the copied text into the "
                    "assistant instead."
                ) from exc
            selection_ranges = text_pattern.GetSelection()
            if selection_ranges is None or selection_ranges.Length == 0:
                raise SelectionUnavailableError(
                    "No text is selected. Select text in the target application "
                    "before pressing Ctrl+Shift+G."
                )
            if selection_ranges.Length != 1:
                raise SelectionUnavailableError(
                    "Multiple text ranges are selected. Select one continuous "
                    "range so a suggestion can be safely applied."
                )

            text_range = selection_ranges.GetElement(0)
            text = text_range.GetText(-1).strip()
            if not text:
                raise SelectionUnavailableError(
                    "The focused control reported an empty text selection. "
                    "You can paste copied text into the assistant instead."
                )
            if len(text) > MAX_SELECTION_LENGTH:
                raise SelectionUnavailableError(
                    f"The selection is {len(text)} characters long; the maximum "
                    f"supported selection is {MAX_SELECTION_LENGTH} characters."
                )
            return text
        except SelectionUnavailableError:
            raise
        except COMError as exc:
            logger.info(
                "UI Automation could not read selected text from window %s: %s",
                target_window,
                exc,
            )
            raise SelectionUnavailableError(
                "This application did not provide the selection through Windows "
                "UI Automation. You can copy the selected text and use "
                "'Paste from clipboard' in the assistant."
            ) from exc
        except (OSError, ImportError) as exc:
            logger.warning("Windows UI Automation could not be initialized: %s", exc)
            raise SelectionUnavailableError(
                "Windows UI Automation is unavailable. Check that the Phase 3 "
                "dependencies are installed, or paste text into the assistant."
            ) from exc
        finally:
            if initialized:
                CoUninitialize()


class SelectionCaptureWorker(QObject):
    selection_ready = Signal(str, int, object)
    selection_failed = Signal(str, int, object)
    finished = Signal()

    def __init__(
        self,
        target_window: int,
        anchor: QPoint,
        reader: WindowsSelectionReader | None = None,
    ) -> None:
        super().__init__()
        self._target_window = target_window
        self._anchor = QPoint(anchor)
        self._reader = reader or WindowsSelectionReader()

    def run(self) -> None:
        try:
            text = self._reader.read_selection(self._target_window)
            self.selection_ready.emit(text, self._target_window, self._anchor)
        except SelectionUnavailableError as exc:
            self.selection_failed.emit(str(exc), self._target_window, self._anchor)
        except Exception as exc:
            logger.exception("Unexpected error while reading selected text")
            self.selection_failed.emit(
                f"Could not read the selection: {exc}",
                self._target_window,
                self._anchor,
            )
        finally:
            self.finished.emit()


class SelectionController(QObject):
    selection_ready = Signal(str, int, object)
    selection_failed = Signal(str, int, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: SelectionCaptureWorker | None = None

    @property
    def is_busy(self) -> bool:
        return self._thread is not None

    def capture(self, target_window: int, anchor: QPoint) -> None:
        if self._thread is not None:
            self.selection_failed.emit(
                "A selection request is already in progress.",
                target_window,
                QPoint(anchor),
            )
            return

        thread = QThread(self)
        worker = SelectionCaptureWorker(target_window, anchor)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.selection_ready.connect(self.selection_ready)
        worker.selection_failed.connect(self.selection_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None

    def shutdown(self) -> None:
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait()


def foreground_window_handle() -> int:
    if sys.platform != "win32":
        raise OSError("Foreground window access is available only on Windows.")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    return int(user32.GetForegroundWindow() or 0)


def cursor_position() -> QPoint:
    if sys.platform != "win32":
        raise OSError("Cursor position access is available only on Windows.")

    point = wintypes.POINT()
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    if not user32.GetCursorPos(ctypes.byref(point)):
        raise ctypes.WinError(ctypes.get_last_error())
    return QPoint(point.x, point.y)


def replace_selection_in_window(target_window: int, text: str) -> None:
    if sys.platform != "win32":
        raise OSError("Selection replacement is available only on Windows.")
    if not target_window or not text:
        raise ValueError("A target window and non-empty replacement text are required.")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.keybd_event.argtypes = [
        wintypes.BYTE,
        wintypes.BYTE,
        wintypes.DWORD,
        ctypes.c_size_t,
    ]
    user32.keybd_event.restype = None

    if not user32.IsWindow(target_window):
        raise OSError(
            "The original application window is no longer available. "
            "The suggestion has not been pasted."
        )
    if not user32.SetForegroundWindow(target_window):
        raise OSError(
            "Windows could not activate the original application. "
            "The suggestion has not been pasted."
        )
    if int(user32.GetForegroundWindow() or 0) != target_window:
        raise OSError(
            "The original application did not regain focus. "
            "The suggestion has not been pasted."
        )

    from PySide6.QtWidgets import QApplication

    QApplication.clipboard().setText(text)

    key_down = 0
    try:
        user32.keybd_event(0x11, 0, 0, 0)
        key_down = 1
        user32.keybd_event(ord("V"), 0, 0, 0)
        user32.keybd_event(ord("V"), 0, 0x0002, 0)
    finally:
        if key_down:
            user32.keybd_event(0x11, 0, 0x0002, 0)
