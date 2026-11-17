from activity_monitor.window_tracker import ActiveWindow


_CATEGORY_TERMS = {
    "Coding": (
        "code",
        "visual studio",
        "vscode",
        "pycharm",
        "devenv",
        "github",
        "terminal",
        "powershell",
        "command prompt",
    ),
    "Learning": ("course", "tutorial", "lesson", "classroom", "learning", "udemy"),
    "Documentation": ("documentation", "docs", "readme", "api reference"),
    "Research": ("research", "paper", "journal", "scholar", "arxiv"),
    "Browsing": ("chrome", "brave", "firefox", "edge", "browser"),
    "Communication": ("teams", "outlook", "mail", "email", "slack"),
}


def classify_activity(window: ActiveWindow) -> str:
    searchable = f"{window.process_name} {window.title}".casefold()
    for category, terms in _CATEGORY_TERMS.items():
        if any(term in searchable for term in terms):
            return category
    return "Other"
