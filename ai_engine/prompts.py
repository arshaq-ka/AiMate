from enum import Enum


class WritingMode(Enum):
    CORRECT_GRAMMAR = "Correct grammar"
    IMPROVE_TONE = "Improve tone"
    PROFESSIONAL = "Make professional"
    FRIENDLY = "Make friendly"
    FORMAL = "Make formal"
    CONCISE = "Make concise"
    SHORTEN = "Shorten sentence"
    REWRITE = "Rewrite"
    EMAIL = "Improve email"


MODE_INSTRUCTIONS = {
    WritingMode.CORRECT_GRAMMAR: (
        "Correct spelling, grammar, punctuation, and obvious usage errors. "
        "Keep the original style where possible."
    ),
    WritingMode.IMPROVE_TONE: (
        "Improve clarity and naturalness while keeping a balanced, neutral tone."
    ),
    WritingMode.PROFESSIONAL: "Rewrite in a clear, professional workplace tone.",
    WritingMode.FRIENDLY: "Rewrite in a warm, friendly, conversational tone.",
    WritingMode.FORMAL: "Rewrite in a polished, formal tone.",
    WritingMode.CONCISE: (
        "Make the text clearer and more concise without removing important details."
    ),
    WritingMode.SHORTEN: (
        "Shorten the text as much as reasonably possible while preserving its meaning."
    ),
    WritingMode.REWRITE: (
        "Rewrite the text for clarity and natural flow without changing its meaning."
    ),
    WritingMode.EMAIL: (
        "Improve the text as an email while preserving its intent and details. "
        "Do not invent a recipient, subject, promise, or facts."
    ),
}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "original_text": {"type": "string"},
        "corrected_text": {"type": "string"},
        "explanation": {"type": "string"},
        "suggested_tone": {"type": "string"},
        "alternatives": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "original_text",
        "corrected_text",
        "explanation",
        "suggested_tone",
        "alternatives",
    ],
    "additionalProperties": False,
}


def build_system_prompt(mode: WritingMode, tone: str | None = None) -> str:
    instruction = MODE_INSTRUCTIONS[mode]
    if mode is WritingMode.IMPROVE_TONE and tone:
        instruction = f"Rewrite in a {tone} tone."
    return (
        "You are a careful writing assistant. Preserve the user's original meaning "
        "and all factual details. Never add unsupported information. Return only "
        "the requested JSON object matching the supplied schema. The original_text "
        "field must exactly match the user's input. Include a short explanation, "
        "a concise description of the resulting tone, and up to two useful "
        "alternative versions. If no change is needed, keep corrected_text equal "
        "to the original_text and say so in the explanation.\n\n"
        f"Requested operation: {instruction}"
    )
