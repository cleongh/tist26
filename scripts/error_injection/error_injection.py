"""
Introduces controlled narrative errors into text excerpts via the DeepSeek API.

This module is intentionally decoupled from text selection: callers provide a
plain ``ErrorInjectionRequest`` with the excerpt (and optional context), and
this module only handles prompt selection, formatting, and the API call.
"""

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum

from .prompts import (
    INJECT_BASIC_COHERENCE,
    INJECT_CAUSALITY,
    INJECT_EMOTIONAL_RELATIONS,
    INJECT_LOCATION_CORRECTNESS,
    INJECT_TEMPORAL_ORDER,
)

logger = logging.getLogger(__name__)

# Read from the environment; never hardcode credentials in source.
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
# Non-reasoning chat model: answers directly instead of spending the token
# budget on hidden chain-of-thought, which reasoning-tier models (e.g. a
# "-pro" variant) were observed to do indefinitely without ever producing
# visible output for this task.
DEEPSEEK_MODEL = "deepseek-chat"

_REQUEST_TIMEOUT_SECONDS = 120
_MAX_RESPONSE_TOKENS = 4096
# Upper bound for the empty-response retry in inject_error(); doubling from
# _MAX_RESPONSE_TOKENS stops once this is reached.
_MAX_RESPONSE_TOKENS_CAP = 16384
# How many extra attempts to make if DeepSeek returns the excerpt unchanged
# (i.e. no error was actually introduced).
_MAX_UNCHANGED_RETRIES = 1
_SYSTEM_MESSAGE = (
    "You rewrite story excerpts to introduce a single controlled narrative "
    "error. Respond directly with the rewritten excerpt only. Do not include "
    "any internal reasoning, analysis, planning, or step-by-step thinking "
    "before or after it."
)


class ErrorType(Enum):
    """Narrative error categories supported by the injection prompts."""

    CAUSALITY = "causality"
    BASIC_COHERENCE = "basic_coherence"
    TEMPORAL_ORDER = "temporal_order"
    LOCATION_CORRECTNESS = "location_correctness"
    EMOTIONAL_RELATIONS = "emotional_relations"


_PROMPT_BY_ERROR_TYPE: dict[ErrorType, str] = {
    ErrorType.CAUSALITY: INJECT_CAUSALITY,
    ErrorType.BASIC_COHERENCE: INJECT_BASIC_COHERENCE,
    ErrorType.TEMPORAL_ORDER: INJECT_TEMPORAL_ORDER,
    ErrorType.LOCATION_CORRECTNESS: INJECT_LOCATION_CORRECTNESS,
    ErrorType.EMOTIONAL_RELATIONS: INJECT_EMOTIONAL_RELATIONS,
}


@dataclass(frozen=True)
class ErrorInjectionRequest:
    """A text excerpt to modify, independent of where it came from.

    ``previous`` and ``follows`` are optional context sentences; leave them
    empty when the excerpt sits at a chapter boundary.
    """

    text: str
    error_type: ErrorType
    previous: str = ""
    follows: str = ""


class DeepSeekAPIError(RuntimeError):
    """Raised when the DeepSeek API call fails or returns an unusable response."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class DeepSeekEmptyResponseError(DeepSeekAPIError):
    """Raised when DeepSeek returns no visible content (e.g. reasoning consumed the budget)."""


class DeepSeekUnchangedResponseError(DeepSeekAPIError):
    """Raised when DeepSeek returns the excerpt unchanged; no error was introduced."""


def _normalize_for_comparison(text: str) -> str:
    """Collapse whitespace for a lenient equality check between input and output."""
    return " ".join(text.split())


def _build_prompt(request: ErrorInjectionRequest) -> str:
    """Select the prompt template for the request's error type and fill it in."""
    template = _PROMPT_BY_ERROR_TYPE[request.error_type]
    return template.format(
        previous=request.previous or "(none — this is the start of the chapter)",
        text=request.text,
        follows=request.follows or "(none — this is the end of the chapter)",
    )


def _call_deepseek_api(prompt: str, api_key: str, max_tokens: int = _MAX_RESPONSE_TOKENS) -> str:
    """Send a chat completion request to DeepSeek and return the reply text."""
    if not api_key:
        raise DeepSeekAPIError(
            "DeepSeek API key is not set. Provide it via the DEEPSEEK_API_KEY "
            "environment variable or the api_key argument."
        )

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_MESSAGE},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": max_tokens,
    }

    http_request = urllib.request.Request(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(http_request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise DeepSeekAPIError(
            f"DeepSeek API returned HTTP {exc.code}: {detail}", status_code=exc.code
        ) from exc
    except urllib.error.URLError as exc:
        raise DeepSeekAPIError(f"Failed to reach DeepSeek API: {exc.reason}") from exc

    try:
        choice = body["choices"][0]
        content = choice["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise DeepSeekAPIError(f"Unexpected DeepSeek API response shape: {body}") from exc

    if not content:
        finish_reason = choice.get("finish_reason")
        reasoning_content = choice.get("message", {}).get("reasoning_content") or ""
        raise DeepSeekEmptyResponseError(
            f"DeepSeek API returned an empty response (finish_reason={finish_reason!r}, "
            f"reasoning_content_length={len(reasoning_content)}, max_tokens={max_tokens}). "
            f"The model may have used the entire token budget on hidden reasoning."
        )

    return content


def inject_error(request: ErrorInjectionRequest, api_key: str | None = None) -> str:
    """
    Rewrite a text excerpt to introduce one controlled narrative error.

    Args:
        request: The excerpt (plus optional surrounding context) and the
            error type to introduce.
        api_key: DeepSeek API key. Defaults to the DEEPSEEK_API_KEY
            environment variable.

    Returns:
        The rewritten excerpt text with the requested error introduced.

    Raises:
        DeepSeekAPIError: If the API call fails or the response is unusable.
    """
    resolved_api_key = api_key if api_key is not None else DEEPSEEK_API_KEY
    prompt = _build_prompt(request)
    logger.debug(
        "Requesting '%s' error injection (%d chars)",
        request.error_type.value,
        len(request.text),
    )

    max_tokens = _MAX_RESPONSE_TOKENS
    unchanged_attempts = 0
    while True:
        try:
            modified_text = _call_deepseek_api(prompt, resolved_api_key, max_tokens=max_tokens)
        except DeepSeekEmptyResponseError:
            if max_tokens >= _MAX_RESPONSE_TOKENS_CAP:
                raise
            max_tokens = min(max_tokens * 2, _MAX_RESPONSE_TOKENS_CAP)
            logger.warning(
                "Empty response from DeepSeek; retrying '%s' with max_tokens=%d",
                request.error_type.value,
                max_tokens,
            )
            continue

        if _normalize_for_comparison(modified_text) == _normalize_for_comparison(request.text):
            if unchanged_attempts >= _MAX_UNCHANGED_RETRIES:
                raise DeepSeekUnchangedResponseError(
                    f"DeepSeek returned the excerpt unchanged for '{request.error_type.value}' "
                    f"after {unchanged_attempts + 1} attempt(s); no error was introduced."
                )
            unchanged_attempts += 1
            logger.warning(
                "DeepSeek returned unchanged text for '%s'; retrying (attempt %d/%d)",
                request.error_type.value,
                unchanged_attempts,
                _MAX_UNCHANGED_RETRIES,
            )
            continue

        return modified_text


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    demo_request = ErrorInjectionRequest(
        text=(
            "Harry walked into the kitchen and grabbed his wand. "
            "Ron was already there, eating breakfast. "
            "They talked about the upcoming match. "
            "Hermione joined them a few minutes later. "
            "She looked worried about the exam. "
            "Together they left for the Great Hall."
        ),
        error_type=ErrorType.LOCATION_CORRECTNESS,
        previous="The morning sun rose over Hogwarts.",
        follows="Classes began an hour later.",
    )

    if not DEEPSEEK_API_KEY:
        logger.warning("DEEPSEEK_API_KEY is not set; printing the prompt instead of calling the API.")
        print(_build_prompt(demo_request))
    else:
        print(inject_error(demo_request))
