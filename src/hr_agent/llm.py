from __future__ import annotations

import math
import re
import time
from typing import TYPE_CHECKING

from hr_agent.config import GROQ_BASE_URL, settings

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

_SYSTEM_PROMPT = "You are a helpful, concise HR policy assistant. Answer only from the provided evidence."

_KEY_ENV = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY"}

_EMBED_BATCH = 100


def llm_available() -> bool:
    """True when the configured generation provider has an API key."""
    return bool(settings.resolved_llm_api_key)


def missing_credentials_message() -> str:
    env = _KEY_ENV.get(settings.provider, "LLM_API_KEY")
    return f"{env} is not configured; used template synthesis instead of the LLM."


def generate_answer(prompt: str, *, model: str | None = None) -> str:
    """Generate a completion from the configured provider.

    ``LLM_PROVIDER=gemini`` uses google-genai. ``groq`` / ``openai_compatible``
    use the OpenAI-style chat API (Groq, OpenRouter, a local Ollama server, ...).
    """
    target_model = model or settings.llm_model
    provider = settings.provider

    if provider == "gemini":
        return _generate_gemini(prompt, target_model)
    if provider in {"groq", "openai_compatible", "openai"}:
        return _generate_openai_compatible(prompt, target_model)
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")


def _generate_gemini(prompt: str, model: str) -> str:
    from google import genai

    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(model=model, contents=prompt)
    text = getattr(response, "text", None)
    return text if text else str(response)


def _generate_openai_compatible(prompt: str, model: str) -> str:
    from openai import OpenAI

    api_key = settings.resolved_llm_api_key
    if not api_key:
        raise ValueError(missing_credentials_message())

    client = OpenAI(api_key=api_key, base_url=settings.resolved_llm_base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content or ""


# --------------------------------------------------------------------------- eval judge


def judge_available() -> bool:
    """True when the configured evaluation judge provider has an API key."""
    provider = settings.eval_judge_provider.strip().lower()
    if provider == "gemini":
        return bool(settings.gemini_api_key)
    if provider == "groq":
        return bool(settings.groq_api_key)
    return False


def judge_complete(
    prompt: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.0,
) -> str:
    """Plain completion from an explicitly chosen provider/model, for the eval judge.

    Independent of ``LLM_PROVIDER`` so the judge can be a different model family
    than the system under test (avoids self-preference bias, separate quota).
    Only ``gemini`` and ``groq`` are wired up. Kept here so ``llm.py`` stays the
    only file importing a model SDK (see CLAUDE.md).
    """
    provider = (provider or settings.eval_judge_provider).strip().lower()
    model = model or settings.eval_judge_model

    if provider == "gemini":
        return _generate_gemini(prompt, model)
    if provider == "groq":
        from openai import OpenAI

        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is not configured (required for the Groq judge).")
        client = OpenAI(api_key=settings.groq_api_key, base_url=GROQ_BASE_URL)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
        )
        return response.choices[0].message.content or ""
    raise ValueError(f"Unsupported eval judge provider: {provider!r}")


# ------------------------------------------------------------------- chat model (tool calling)


def chat_model(*, temperature: float = 0.0) -> BaseChatModel:
    """Return a LangChain chat model for the configured provider.

    The agent loop needs ``.bind_tools()`` and structured ``AIMessage.tool_calls``,
    which the raw ``generate_answer`` string path does not give us. This is the
    only place the provider *chat* SDKs are imported, so ``LLM_PROVIDER`` stays the
    single switch (see CLAUDE.md).
    """
    provider = settings.provider
    model = settings.llm_model
    api_key = settings.resolved_llm_api_key
    if not api_key:
        raise ValueError(missing_credentials_message())

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            temperature=temperature,
            max_output_tokens=settings.llm_max_output_tokens,
        )
    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=settings.llm_max_output_tokens,
        )
    if provider in {"openai_compatible", "openai"}:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=settings.resolved_llm_base_url,
            temperature=temperature,
            max_tokens=settings.llm_max_output_tokens,
        )
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")


# --------------------------------------------------------------------------- embeddings


def embedding_available() -> bool:
    """Embeddings always use Gemini here, regardless of the generation provider."""
    return bool(settings.gemini_api_key)


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


def _retry_delay_seconds(exc: Exception, attempt: int) -> float:
    """Honour the server's suggested delay if present, else exponential backoff."""
    match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+(?:\.\d+)?)s", str(exc))
    if match:
        return float(match.group(1)) + 1.0
    return min(2.0**attempt, 30.0)


def _embed_batch(client, model: str, batch: list[str], config, *, retries: int = 5) -> list:
    from google.genai.errors import ClientError

    for attempt in range(retries + 1):
        try:
            return client.models.embed_content(model=model, contents=batch, config=config).embeddings
        except ClientError as exc:
            if getattr(exc, "code", None) != 429 or attempt == retries:
                raise
            time.sleep(_retry_delay_seconds(exc, attempt))
    raise RuntimeError("unreachable")


def embed(texts: list[str], *, task_type: str = "retrieval_document") -> list[list[float]]:
    """Embed a list of texts with Gemini, L2-normalised so cosine == dot product.

    ``task_type`` is ``retrieval_document`` for corpus chunks and
    ``retrieval_query`` for a user's question -- Gemini tunes each side of an
    asymmetric search differently. Batched, with retry/backoff on 429.
    """
    from google import genai
    from google.genai import types

    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not configured (required for embeddings).")
    if not texts:
        return []

    client = genai.Client(api_key=settings.gemini_api_key)
    config = types.EmbedContentConfig(
        task_type=task_type.upper(),
        output_dimensionality=settings.embedding_dim,
    )

    vectors: list[list[float]] = []
    for start in range(0, len(texts), _EMBED_BATCH):
        batch = texts[start : start + _EMBED_BATCH]
        embeddings = _embed_batch(client, settings.embedding_model, batch, config)
        vectors.extend(_l2_normalize(list(item.values)) for item in embeddings)
    return vectors
