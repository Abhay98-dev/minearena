"""Local providers: Ollama (real local SLM, optional fallback) and Mock (offline demo/tests)."""
import os
import re

from app.core import config
from .base import LLMError, LLMProvider, LLMTimeout, SYSTEM_PROMPT

_PH = re.compile(r"<[A-Z_]+_\d+>")


class OllamaProvider(LLMProvider):
    """Needs `ollama serve` + `ollama pull <model>`. No API key, nothing leaves the machine."""
    name = "ollama"

    def __init__(self):
        self.model = config.OLLAMA_MODEL

    async def generate(self, text: str, task: str) -> str:
        import httpx
        body = {"model": self.model, "system": SYSTEM_PROMPT, "prompt": self.build_payload(text, task), "stream": False}
        try:
            async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT_S * 3) as c:
                r = await c.post(f"{config.OLLAMA_URL}/api/generate", json=body)
        except httpx.TimeoutException as e:
            raise LLMTimeout("timeout") from e
        except httpx.HTTPError as e:
            raise LLMError("network") from e
        if r.status_code != 200:
            raise LLMError(f"http_{r.status_code}")
        out = r.json().get("response", "")
        if not out.strip():
            raise LLMError("empty_response")
        return out


class MockProvider(LLMProvider):
    """Deterministic stand-in. MOCK_MODE: echo | reorder | drop | paraphrase | unknown | fail | timeout.
    Used to demo reinsertion robustness and to run the pipeline without an API key."""
    name = "mock"
    model = "mock-llm-1"

    async def generate(self, text: str, task: str) -> str:
        mode = os.getenv("MOCK_MODE", "echo")
        if mode == "fail":
            raise LLMError("http_500")
        if mode == "timeout":
            raise LLMTimeout("timeout")
        phs = list(dict.fromkeys(_PH.findall(text)))
        if mode == "reorder":
            return "Details: " + " and ".join(reversed(phs)) + "."
        if mode == "drop":
            return "The applicant submitted an application." + (f" Ref {phs[1]}." if len(phs) > 1 else "")
        if mode == "paraphrase":
            return f"The applicant, {phs[0]}, " + ("holds " + ", ".join(phs[1:]) + "." if len(phs) > 1 else "applied.") if phs else "No data."
        if mode == "unknown":
            return " ".join(phs) + " <EMAIL_9> <PERSON_99>"
        return "Summary: " + " | ".join(phs) if phs else "Summary: " + text[:80]
