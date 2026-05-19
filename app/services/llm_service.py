"""Gemini-backed narrative generation for reconciliation summaries."""

import json
import os
import warnings
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from dotenv import load_dotenv

with warnings.catch_warnings():
    warnings.simplefilter("ignore", FutureWarning)
    import google.generativeai as genai


ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "summary_prompt.txt"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"


class LLMServiceError(RuntimeError):
    """Base error for LLM summary generation failures."""


class LLMConfigurationError(LLMServiceError):
    """Raised when required Gemini configuration is missing."""


def generate_reconciliation_summary(
    reconciliation_json: Mapping[str, Any],
) -> str:
    """Generate a concise narrative from deterministic reconciliation JSON."""
    prompt = build_summary_prompt(reconciliation_json)
    model = _build_gemini_model()

    try:
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.2,
                "max_output_tokens": 256,
            },
        )
        summary = getattr(response, "text", "").strip()
    except Exception as exc:
        raise LLMServiceError("Gemini summary generation failed.") from exc

    if not summary:
        raise LLMServiceError("Gemini returned an empty summary.")

    return summary


def build_summary_prompt(reconciliation_json: Mapping[str, Any]) -> str:
    """Build the Gemini prompt from structured reconciliation JSON."""
    prompt_template = _load_summary_prompt_template()
    serialized_json = json.dumps(
        reconciliation_json,
        indent=2,
        sort_keys=True,
        default=_json_default,
    )
    return prompt_template.format(reconciliation_json=serialized_json)


def _load_summary_prompt_template() -> str:
    """Load the external reconciliation summary prompt template."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def _build_gemini_model() -> genai.GenerativeModel:
    """Configure and return the Gemini model client."""
    load_dotenv(dotenv_path=ENV_PATH)
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

    if not api_key:
        raise LLMConfigurationError("GEMINI_API_KEY is not configured.")

    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name)


def _json_default(value: Any) -> float:
    """Serialize Decimal values for prompt JSON."""
    if isinstance(value, Decimal):
        return float(value)

    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
