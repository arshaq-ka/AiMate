from typing import Any

from ai_engine.ollama_client import OllamaWritingClient
from ai_engine.prompts import WritingMode


def correct_grammar(client: OllamaWritingClient, text: str) -> dict[str, Any]:
    return client.rewrite(text, WritingMode.CORRECT_GRAMMAR)
