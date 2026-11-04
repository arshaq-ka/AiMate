import ctypes
import logging
import sys
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter

logger = logging.getLogger(__name__)

HOTKEY_ID = 0xA17E
WM_HOTKEY = 0x0312
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000


class ShortcutUnavailableError(RuntimeError):
    """Raised when the requested system-wide shortcut cannot be registered."""


def _native_message_address(message) -> int | None:
    if isinstance(message, int):
        return message

    try:
        address = int(message)
    except (TypeError, ValueError):
        address = ctypes.cast(message, ctypes.c_void_p).value
    return address or None


class _Point(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class _Message(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", _Point),
    ]


class GlobalShortcut(QAbstractNativeEventFilter):
    """Register Ctrl+Shift+G without observing or recording other keystrokes."""

    def __init__(self, callback: Callable[[], None]) -> None:
        super().__init__()
        if sys.platform != "win32":
            raise ShortcutUnavailableError(
                "The global shortcut is available only on Windows."
            )

        self._callback = callback
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        register_hotkey = self._user32.RegisterHotKey
        register_hotkey.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            wintypes.UINT,
            wintypes.UINT,
        ]
        register_hotkey.restype = wintypes.BOOL
        if not register_hotkey(
            None,
            HOTKEY_ID,
            MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT,
            ord("G"),
        ):
            error = ctypes.get_last_error()
            if error == 1409:
                reason = "Ctrl+Shift+G is already registered by another application."
            else:
                reason = ctypes.FormatError(error).strip()
            raise ShortcutUnavailableError(
                f"Could not register Ctrl+Shift+G: {reason}"
            )

        self._registered = True

    def nativeEventFilter(self, event_type, message):  # noqa: N802 - Qt override
        if event_type not in (
            b"windows_generic_MSG",
            b"windows_dispatcher_MSG",
        ):
            return False, 0

        try:
            address = _native_message_address(message)
            if not address:
                return False, 0
            native_message = ctypes.cast(
                address, ctypes.POINTER(_Message)
            ).contents
        except (TypeError, ValueError, ctypes.ArgumentError):
            logger.exception("Could not read a Windows native message")
            return False, 0

        if native_message.message != WM_HOTKEY or native_message.wParam != HOTKEY_ID:
            return False, 0

        try:
            self._callback()
        except Exception:
            logger.exception("Global shortcut callback failed")
        return True, 0

    def unregister(self) -> None:
        if getattr(self, "_registered", False):
            if not self._user32.UnregisterHotKey(None, HOTKEY_ID):
                logger.warning(
                    "Could not unregister Ctrl+Shift+G: %s",
                    ctypes.FormatError(ctypes.get_last_error()).strip(),
                )
            self._registered = False
