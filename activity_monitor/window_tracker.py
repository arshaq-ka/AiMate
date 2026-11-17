import ctypes
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass


@dataclass(frozen=True)
class ActiveWindow:
    handle: int
    process_name: str
    title: str


def get_active_window() -> ActiveWindow | None:
    if sys.platform != "win32":
        raise OSError("Active window tracking is available only on Windows.")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [
        wintypes.HWND,
        wintypes.LPWSTR,
        ctypes.c_int,
    ]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = user32.GetForegroundWindow()
    if not handle:
        return None

    length = user32.GetWindowTextLengthW(handle)
    title_buffer = ctypes.create_unicode_buffer(max(length + 1, 2))
    user32.GetWindowTextW(handle, title_buffer, len(title_buffer))

    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
    process_handle = kernel32.OpenProcess(0x1000, False, process_id.value)
    if not process_handle:
        process_name = "unknown"
    else:
        try:
            path_buffer = ctypes.create_unicode_buffer(32768)
            path_length = wintypes.DWORD(len(path_buffer))
            if kernel32.QueryFullProcessImageNameW(
                process_handle,
                0,
                path_buffer,
                ctypes.byref(path_length),
            ):
                process_name = os.path.basename(path_buffer.value).lower()
            else:
                process_name = "unknown"
        finally:
            kernel32.CloseHandle(process_handle)

    return ActiveWindow(int(handle), process_name, title_buffer.value)
