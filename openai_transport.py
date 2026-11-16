"""Single-attempt, non-storing transport shared by the optional OpenAI features."""

from __future__ import annotations

import json
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from stock_data import StockDataError


MAX_RESPONSE_BYTES = 256_000


def response_text(response: Any, *, max_chars: int) -> str:
    if not isinstance(response, dict) or response.get("status") != "completed" or response.get("error"):
        raise StockDataError("OpenAI did not complete the answer. Retry explicitly.")
    output = response.get("output")
    if not isinstance(output, list):
        raise StockDataError("OpenAI returned an invalid answer. Retry explicitly.")
    texts = []
    for item in output:
        if not isinstance(item, dict):
            raise StockDataError("OpenAI returned an invalid answer. Retry explicitly.")
        if item.get("type") == "reasoning":
            continue
        if (
            item.get("type") != "message"
            or item.get("role", "assistant") != "assistant"
            or item.get("status", "completed") != "completed"
            or not isinstance(item.get("content"), list)
        ):
            raise StockDataError("OpenAI returned an invalid answer. Retry explicitly.")
        for part in item["content"]:
            if isinstance(part, dict) and part.get("type") == "refusal":
                raise StockDataError("OpenAI declined to answer this question. Try a different question.")
            if (
                not isinstance(part, dict) or part.get("type") != "output_text"
                or not isinstance(part.get("text"), str) or not part["text"].strip()
            ):
                raise StockDataError("OpenAI returned an invalid answer. Retry explicitly.")
            texts.append(part["text"].strip())
    answer = "\n\n".join(texts)
    if not answer or len(answer) > max_chars:
        raise StockDataError("OpenAI returned an empty or oversized answer. Retry explicitly.")
    return answer


def _reject_constant(value: str) -> None:
    raise ValueError("Nonfinite JSON number")


def request_openai_response(payload: dict[str, Any], api_key: str) -> Any:
    """Send exactly once. Never expose upstream bodies, credentials or exception text."""
    if not isinstance(api_key, str) or not api_key.strip():
        raise StockDataError("Set an OpenAI API key locally to enable this feature.")
    try:
        request = Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps({**payload, "store": False}, allow_nan=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=90) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError("Response too large")
        return json.loads(body, parse_constant=_reject_constant)
    except HTTPError as exc:
        code = exc.code
        exc.close()
        explanations = {
            401: "The API key was rejected.",
            403: "This API key does not have access.",
            429: "Rate limit or API quota reached; check billing before retrying.",
        }
        detail = explanations.get(code, "Check model access and service availability.")
        raise StockDataError(f"OpenAI request failed (HTTP {code}). {detail}") from None
    except (OSError, ValueError, TypeError, HTTPException):
        raise StockDataError(
            "OpenAI could not be reached or returned unreadable data. Retry explicitly."
        ) from None
