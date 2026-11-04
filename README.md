# Local AI Desktop Companion

The project currently implements Phase 1 (the floating character), Phase 2
(local Ollama writing assistance), and Phase 3 (explicit selected-text
assistance). Text is sent only to the local Ollama service on this computer.
Nothing is sent to a cloud AI service. Suggestions are never inserted into
another application without an explicit Replace action.

## Requirements

- Windows 10/11 with a system tray
- Python 3.10 or newer (developed with Python 3.13)
- Ollama installed and running locally
- A Llama 3.2 model installed in Ollama
- Windows UI Automation support in the target application

## Install and run

From PowerShell in the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Only one companion instance can run at a time. If an older copy is already
running, quit it from its tray icon before launching the updated app.

The app recognizes `llama3.2:3b` and `llama3.2:latest`. If both are installed,
it prefers `llama3.2:3b`; if neither is installed, it explains how to install
one. This workspace has `llama3.2:latest` installed; Ollama reports it as a
3.2B model. To install the other tag:

```powershell
ollama pull llama3.2:3b
```

Ollama must be running before requesting suggestions. The model stays loaded
for five minutes after a request, then Ollama can unload it to release memory.
For privacy, the app connects only to a loopback Ollama host and bypasses
system HTTP proxies. You can select another installed model with the
`COMPANION_OLLAMA_MODEL` environment variable.

## Phase 1 controls

- **Drag with the left mouse button** to reposition the character.
- **Right-click the character** for animation controls, the writing assistant,
  Hide, and Quit.
- **Right-click the tray icon** for Show/Hide, writing assistant,
  Pause/Resume animation, and Quit.
- **Double-click the tray icon** to toggle character visibility.
- **Close the character window** to hide it; use tray **Quit** to exit.
- **Quit** from either the character menu or tray menu exits the entire app.

## Phase 2 writing assistant

Open **Writing assistant** from the character's right-click menu or the tray
menu. The window checks the local Ollama service and model asynchronously.
Enter or paste text, choose an operation, and select **Get suggestion**.

Supported operations: correct grammar, improve tone, professional, friendly,
formal, concise, shorten, rewrite, and email improvement. The result includes
the suggested text, explanation, suggested tone, and up to two alternatives.
Use **Copy corrected text** to explicitly copy the main suggestion; the app
does not modify the source text.

AI inference runs in a worker thread so the character and UI remain responsive.
The character displays **THINKING** while a suggestion is being generated.
Empty input, excessive input, Ollama connection issues, missing models, and
malformed model output are shown as errors in the writing window.

## Phase 3 text selection

The app registers the Windows global shortcut **Ctrl+Shift+G**. Select text in
a supported application and press the shortcut to read that selection through
Windows UI Automation. The writing window opens near the cursor with the
selected text loaded and starts a grammar suggestion. To try a different
operation, choose it from the list and click **Get suggestion**.

Use **Copy corrected text** to copy a suggestion, or **Replace selected text**
to explicitly paste it over the originally selected text in the source window.
Replacement is only enabled when UI Automation confirmed an actual selection;
text entered manually or pasted from the clipboard cannot be used to replace a
source selection. If an app does not expose its text selection to UI
Automation, copy the text yourself and click **Paste from clipboard** in the
assistant. Clipboard contents are not read automatically. The app does not
record keystrokes or poll what you type.

Browser and editor accessibility varies; some controls do not expose selection
through UI Automation. The shortcut may also be unavailable if another
application already registered Ctrl+Shift+G; the tray displays a warning and
the assistant remains available from its menus.

## Tests

Run the automated Phase 1, Phase 2, and Phase 3 unit tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

These tests verify character behavior, model selection, writing requests,
background responsiveness, selection handling, and safe clipboard fallback.
Mocked tests do not require Ollama or make a real model request.

To manually test the real local integration:

1. Confirm Ollama is running: `ollama list`.
2. Launch the app with `.\.venv\Scripts\python.exe main.py`.
3. Open **Writing assistant** from either right-click menu.
4. Paste `I am not able to attend meeting because i have some work.`
5. Choose **Correct grammar** and click **Get suggestion**.
6. Confirm the corrected text and explanation appear while the character shows
   **THINKING** during processing.
7. Click **Copy corrected text** and paste into Notepad to verify the clipboard.
8. Try a tone option, then stop Ollama and verify the writing window reports a
   connection error without freezing the app.

To manually test Phase 3:

1. Quit any old companion copy, then launch the updated app with
   `.\.venv\Scripts\python.exe main.py`.
2. Open Notepad.
3. Type and select `I am not able to attend meeting because i have some work.`
4. Press **Ctrl+Shift+G**. The writing window should open with the selection
   loaded.
5. Review the automatically generated grammar suggestion. Optionally select a
   different operation and click **Get suggestion** again.
6. Confirm the suggestion is displayed. Use **Copy corrected text** and paste
   into another document, or click **Replace selected text** to explicitly
   replace the selected sentence in Notepad.
7. Try an application that may not expose UIA text selection. Copy text
   manually, trigger the shortcut, and use **Paste from clipboard**.

## Project files

- `main.py` — application startup, tray integration, and graceful shutdown.
- `character/` — animated character, state, and tray UI.
- `ai_engine/ollama_client.py` — local model discovery and structured generation.
- `ai_engine/prompts.py` — writing modes, prompt instructions, and JSON schema.
- `ai_engine/grammar.py` — grammar correction service entry point.
- `ai_engine/tone.py` — tone/rewrite service entry point.
- `text_assistant/writing_window.py` — writing UI and background worker.
- `text_assistant/selection.py` — on-demand UI Automation selection and
  explicit replace/clipboard actions.
- `text_assistant/shortcuts.py` — Windows Ctrl+Shift+G registration.
- `tests/` — automated Phase 1, Phase 2, and Phase 3 tests.
- `requirements.txt` — PySide6 and Ollama client dependencies.

Activity monitoring, database storage, and document generation are later
phases and are not implemented yet.
