from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone

from google import genai
from google.genai import types

from src.ai.prompts import SYSTEM_PROMPT
from src.models import RawItem

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"
FALLBACK_MODELS = ("gemini-2.5-flash", "gemini-2.0-flash-lite", "gemini-2.0-flash")
MAX_RETRIES = 3
MAX_SOURCE_LINKS = 20


def _build_payload(items: list[RawItem]) -> str:
    blocks = []
    for item in items:
        source = item.source.upper()
        if item.source == "youtube" and item.metadata.get("channel_name"):
            source = f"{source} / {item.metadata['channel_name']}"
        blocks.append(
            "\n".join(
                [
                    f"[{source}] {item.title}",
                    item.body[:500],
                    f"URL: {item.url}",
                    f"Data: {item.published_at.isoformat()}",
                ]
            )
        )
    return "\n---\n".join(blocks)


def _source_label(item: RawItem) -> str:
    if item.source == "youtube" and item.metadata.get("channel_name"):
        return str(item.metadata["channel_name"])
    if item.source == "twitter" and item.metadata.get("username"):
        return f"@{item.metadata['username']}"
    return item.source


def _append_source_links(text: str, items: list[RawItem]) -> str:
    if not items or "Links analisados" in text:
        return text

    lines = ["", "🔗 *Links analisados*"]
    for item in items[:MAX_SOURCE_LINKS]:
        lines.append(f"- {_source_label(item)}: {item.title[:90]}")
        lines.append(item.url)

    return f"{text.rstrip()}\n" + "\n".join(lines)


def _models_to_try(model: str | None) -> list[str]:
    if model:
        return [model, *(m for m in FALLBACK_MODELS if m != model)]
    env_model = os.environ.get("GEMINI_MODEL")
    if env_model:
        return [env_model, *(m for m in FALLBACK_MODELS if m != env_model)]
    return list(FALLBACK_MODELS)


def _retry_delay_seconds(exc: Exception, attempt: int) -> float:
    match = re.search(r"retry in (\d+(?:\.\d+)?)s", str(exc), re.IGNORECASE)
    if match:
        return float(match.group(1)) + 1
    return float(2**attempt)


def _is_quota_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "429" in message or "resource_exhausted" in message or "quota" in message


def fallback_summarize(items: list[RawItem]) -> str:
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    lines = [
        f"⚽ *Relatório Galo — {today}*",
        "",
        "_Resumo automático (Gemini indisponível — quota esgotada ou API key sem acesso)._",
        "",
    ]
    for item in items[:8]:
        title = item.title[:60]
        snippet = item.body[:120].replace("\n", " ").strip()
        if snippet:
            lines.extend([f"• *{title}*", snippet, item.url, ""])
        else:
            lines.extend([f"• *{title}*", item.url, ""])
    lines.append("_Fontes: YouTube, X — gerado automaticamente_")
    return "\n".join(lines)


def summarize(items: list[RawItem], api_key: str, model: str | None = None) -> str:
    client = genai.Client(api_key=api_key)
    payload = _build_payload(items)
    prompt = f"{SYSTEM_PROMPT}\n\nDados brutos:\n\n{payload}"

    last_error: Exception | None = None
    for candidate_model in _models_to_try(model):
        for attempt in range(MAX_RETRIES):
            try:
                response = client.models.generate_content(
                    model=candidate_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=2048,
                    ),
                )
                text = response.text
                if not text:
                    raise ValueError("Gemini returned an empty response")
                if candidate_model != (model or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL):
                    logger.info("Summarized with fallback model %s", candidate_model)
                return _append_source_links(text.strip(), items)
            except Exception as exc:
                last_error = exc
                if attempt == MAX_RETRIES - 1:
                    logger.warning(
                        "Gemini model %s failed after %s attempts: %s",
                        candidate_model,
                        MAX_RETRIES,
                        exc,
                    )
                    break
                wait_seconds = _retry_delay_seconds(exc, attempt)
                logger.warning(
                    "Gemini request failed (model=%s, attempt %s/%s): %s. Retrying in %ss.",
                    candidate_model,
                    attempt + 1,
                    MAX_RETRIES,
                    exc,
                    wait_seconds,
                )
                time.sleep(wait_seconds)

    if last_error and _is_quota_error(last_error):
        logger.error(
            "Gemini quota exhausted for all models. Using plain-text fallback. "
            "Check billing at https://aistudio.google.com or set GEMINI_MODEL in .env"
        )
        return fallback_summarize(items)

    raise RuntimeError("Failed to summarize content with Gemini") from last_error
