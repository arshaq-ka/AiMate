import json
import os
from typing import Any
from urllib.parse import urlsplit

import httpx
import ollama

from ai_engine.prompts import RESPONSE_SCHEMA, WritingMode, build_system_prompt


DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL_CANDIDATES = ("llama3.2:3b", "llama3.2:latest", "llama3.2")
MAX_INPUT_LENGTH = 12000


class OllamaUnavailableError(RuntimeError):
    """Raised when the local Ollama service or a usable model is unavailable."""


class OllamaResponseError(RuntimeError):
    """Raised when Ollama returns an invalid writing-assistance response."""


class OllamaWritingClient:
    def __init__(
        self,
        host: str | None = None,
        model: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.host = host or DEFAULT_HOST
        parsed_host = urlsplit(self.host)
        try:
            port = parsed_host.port
        except ValueError as exc:
            raise ValueError("Ollama host must use a valid local URL and port.") from exc
        if (
            parsed_host.scheme not in ("http", "https")
            or parsed_host.hostname not in ("127.0.0.1", "localhost", "::1")
            or parsed_host.username is not None
            or parsed_host.password is not None
            or parsed_host.path not in ("", "/")
            or parsed_host.query
            or parsed_host.fragment
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ValueError(
                "For privacy, Ollama must use a loopback host "
                "(127.0.0.1, localhost, or ::1)."
            )
        self.requested_model = model or os.environ.get("COMPANION_OLLAMA_MODEL")
        self._client = (
            client
            if client is not None
            else ollama.Client(
                host=self.host,
                timeout=120,
                trust_env=False,
                follow_redirects=False,
            )
        )
        self.model: str | None = None

    def check_model(self) -> str:
        try:
            response = self._client.list()
        except (ollama.ResponseError, httpx.HTTPError, OSError) as exc:
            raise OllamaUnavailableError(
                f"Cannot connect to Ollama at {self.host}. Start Ollama and try "
                "again. Details: "
                f"{exc}"
            ) from exc

        model_names = [
            str(getattr(item, "model", None) or getattr(item, "name", ""))
            for item in response.models
        ]
        model_names = [name for name in model_names if name]

        if self.requested_model:
            if self.requested_model not in model_names:
                available = ", ".join(model_names) or "none"
                raise OllamaUnavailableError(
                    f"Model '{self.requested_model}' is not installed. Available "
                    f"models: {available}. Install it with "
                    f"'ollama pull {self.requested_model}' or set "
                    "COMPANION_OLLAMA_MODEL to an installed model."
                )
            self.model = self.requested_model
            return self.model

        for candidate in DEFAULT_MODEL_CANDIDATES:
            if candidate in model_names:
                self.model = candidate
                return candidate

        available = ", ".join(model_names) or "none"
        raise OllamaUnavailableError(
            "No Llama 3.2 model was found. Install one with "
            "'ollama pull llama3.2:3b'. "
            f"Models currently available: {available}."
        )

    def rewrite(
        self,
        text: str,
        mode: WritingMode,
        tone: str | None = None,
    ) -> dict[str, Any]:
        if not text.strip():
            raise ValueError("Enter some text before requesting a suggestion.")
        if len(text) > MAX_INPUT_LENGTH:
            raise ValueError(
                f"Text is too long ({len(text)} characters). The limit is "
                f"{MAX_INPUT_LENGTH} characters."
            )
        if self.model is None:
            self.check_model()

        try:
            response = self._client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": build_system_prompt(mode, tone),
                    },
                    {
                        "role": "user",
                        "content": f"Text to transform:\n<text>\n{text}\n</text>",
                    },
                ],
                format=RESPONSE_SCHEMA,
                options={"temperature": 0.2, "num_ctx": 4096, "num_predict": 700},
                keep_alive="5m",
            )
        except (ollama.ResponseError, httpx.HTTPError, OSError) as exc:
            raise OllamaUnavailableError(
                f"Ollama could not generate a suggestion using {self.model}. "
                f"Details: {exc}"
            ) from exc

        content = response.message.content
        try:
            result = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise OllamaResponseError(
                "Ollama returned an unreadable response. Please try again."
            ) from exc

        required_fields = (
            "original_text",
            "corrected_text",
            "explanation",
            "suggested_tone",
            "alternatives",
        )
        if (
            not isinstance(result, dict)
            or any(not isinstance(result.get(key), str) for key in required_fields[:-1])
            or not isinstance(result.get("alternatives"), list)
            or any(not isinstance(item, str) for item in result["alternatives"])
        ):
            raise OllamaResponseError(
                "Ollama returned a response that did not match the expected "
                "writing-suggestion format. Please try again."
            )

        if not result["corrected_text"].strip():
            raise OllamaResponseError(
                "Ollama returned an empty suggestion. Please try again."
            )

        # Return the exact submitted text even if the model altered this metadata.
        result["original_text"] = text
        result["alternatives"] = list(
            dict.fromkeys(
                alternative.strip()
                for alternative in result["alternatives"]
                if alternative.strip()
                and alternative.strip() != result["corrected_text"].strip()
            )
        )[:2]
        return result
