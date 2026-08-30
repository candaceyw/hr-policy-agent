from __future__ import annotations

from google import genai

from hr_agent.config import settings


def generate_answer(prompt: str, *, model: str | None = None) -> str:
    """Generate a final answer with Gemini when an API key is configured."""
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    client = genai.Client(api_key=settings.gemini_api_key)
    target_model = model or settings.llm_model
    response = client.models.generate_content(model=target_model, contents=prompt)

    if hasattr(response, "text") and response.text:
        return response.text
    return str(response)
