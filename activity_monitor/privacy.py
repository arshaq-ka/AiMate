from dataclasses import dataclass
import sys

from activity_monitor.window_tracker import ActiveWindow

DEFAULT_EXCLUDED_PROCESS_NAMES = (
    "chatgpt.exe",
    "discord.exe",
    "ms-teams.exe",
    "outlook.exe",
    "skype.exe",
    "slack.exe",
    "signal.exe",
    "teams.exe",
    "telegram.exe",
    "whatsapp.exe",
)

_SENSITIVE_TITLE_TERMS = (
    "activity monitoring privacy",
    "chatgpt",
    "local activity review",
    "local ai desktop companion",
    "local writing assistant",
    "incognito",
    "inprivate",
    "private browsing",
    "private chat",
    "private message",
    "password",
    "passcode",
    "bank statement",
    "bank",
    "banking",
    "credit card",
    "payment",
    "checkout",
    "wallet",
    "tax return",
    "medical record",
    "health record",
    "inbox",
)


@dataclass(frozen=True)
class PrivacyDecision:
    allowed: bool
    reason: str = ""


def check_window_privacy(
    window: ActiveWindow,
    excluded_process_names: set[str],
    excluded_title_terms: set[str],
) -> PrivacyDecision:
    process_name = window.process_name.casefold()
    if process_name in DEFAULT_EXCLUDED_PROCESS_NAMES:
        return PrivacyDecision(False, "private messaging application")
    if process_name in {name.casefold() for name in excluded_process_names}:
        return PrivacyDecision(False, "application is on the exclusion list")

    title = window.title.casefold()
    sensitive_term = next(
        (term for term in _SENSITIVE_TITLE_TERMS if term in title),
        None,
    )
    if sensitive_term:
        return PrivacyDecision(False, "window title appears sensitive")
    excluded_term = next(
        (term for term in excluded_title_terms if term.casefold() in title),
        None,
    )
    if excluded_term:
        return PrivacyDecision(False, "window title matches an exclusion")
    return PrivacyDecision(True)


def focused_control_is_password(window_handle: int) -> bool:
    if sys.platform != "win32":
        raise OSError("Password-field detection is available only on Windows.")

    from comtypes import CoInitialize, CoUninitialize
    from comtypes.client import CreateObject, GetModule

    initialized = False
    try:
        CoInitialize()
        initialized = True
        GetModule("UIAutomationCore.dll")
        from comtypes.gen.UIAutomationClient import (
            CUIAutomation,
            IUIAutomation,
            UIA_IsPasswordPropertyId,
        )

        automation = CreateObject(CUIAutomation, interface=IUIAutomation)
        element = automation.GetFocusedElement()
        if element is None:
            raise RuntimeError("The focused control could not be checked for privacy.")
        return bool(element.GetCurrentPropertyValue(UIA_IsPasswordPropertyId))
    finally:
        if initialized:
            CoUninitialize()
