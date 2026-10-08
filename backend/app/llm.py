"""Bedrock Claude client wrapper for the Intelligent Workflow Manager.

Thin layer over AnthropicBedrock. The agent layer uses `chat()` for a single
grounded turn and `run_tools()` for the tool-calling loop. All numbers the AI
cites come from engine tools; this module never computes metrics.
"""
from __future__ import annotations

import os

from anthropic import AnthropicBedrock

from . import config


def _make_client() -> AnthropicBedrock:
    """Build an AnthropicBedrock client.

    The AWS_BEARER_TOKEN_BEDROCK env var is read by boto3's credential chain,
    which the Anthropic Bedrock client uses under the hood. We also pass the
    region explicitly.
    """
    # Ensure the token is visible in the environment for the underlying signer.
    if config.BEDROCK_BEARER_TOKEN:
        os.environ.setdefault("AWS_BEARER_TOKEN_BEDROCK", config.BEDROCK_BEARER_TOKEN)
    return AnthropicBedrock(aws_region=config.AWS_REGION)


_client: AnthropicBedrock | None = None


def client() -> AnthropicBedrock:
    global _client
    if _client is None:
        _client = _make_client()
    return _client


def chat(
    messages: list[dict],
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 2048,
    tools: list[dict] | None = None,
):
    """One Messages API turn against Bedrock. Returns the raw response object."""
    kwargs: dict = {
        "model": model or config.MODEL_PRIMARY,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = tools
    return client().messages.create(**kwargs)


def probe(model_id: str) -> tuple[bool, str]:
    """Try a one-token round-trip against a given model id. Returns (ok, detail)."""
    try:
        resp = client().messages.create(
            model=model_id,
            max_tokens=16,
            messages=[{"role": "user", "content": "Reply with the single word: pong"}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return True, text.strip()
    except Exception as e:  # noqa: BLE001 - probe wants the message, not a raise
        return False, f"{type(e).__name__}: {e}"
