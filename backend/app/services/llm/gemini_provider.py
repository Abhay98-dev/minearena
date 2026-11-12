"""Gemini via REST (generateContent). Key goes in header, never in URL/logs.
NOT exercised offline: run the smoke test in the guide with your key before relying on it."""
from app.core import config
from .base import LLMError, LLMProvider, LLMTimeout, SYSTEM_PROMPT


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self):
        self.model = config.GEMINI_MODEL

    async def generate(self, text: str, task: str) -> str:
        import httpx  # lazy
        if not config.GEMINI_API_KEY:
            raise LLMError("missing_api_key")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": self.build_payload(text, task)}]}],
            "generationConfig": {"temperature": 0.2},
        }
        try:
            async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT_S) as c:
                r = await c.post(url, json=body, headers={"x-goog-api-key": config.GEMINI_API_KEY})
        except httpx.TimeoutException as e:
            raise LLMTimeout("timeout") from e
        except httpx.HTTPError as e:
            raise LLMError("network") from e
        if r.status_code != 200:
            raise LLMError(f"http_{r.status_code}")
        try:
            out = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            raise LLMError("malformed_response") from e
        if not out or not out.strip():
            raise LLMError("empty_response")
        return out
