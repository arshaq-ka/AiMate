from typing import Any

from ai_engine.ollama_client import OllamaWritingClient
from ai_engine.prompts import WritingMode


def improve_tone(
    client: OllamaWritingClient,
    text: str,
    mode: WritingMode,
    tone: str | None = None,
) -> dict[str, Any]:
    if mode is WritingMode.CORRECT_GRAMMAR:
        raise ValueError("Use the grammar operation for grammar-only correction.")
    return client.rewrite(text, mode, tone)
