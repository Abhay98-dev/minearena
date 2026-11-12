from app.core.errors import GatewayError
from .base import LLMProvider
from .gemini_provider import GeminiProvider
from .local_providers import MockProvider, OllamaProvider

_REGISTRY = {"gemini": GeminiProvider, "ollama": OllamaProvider, "mock": MockProvider}


def get_provider(name: str, request_id: str = None) -> LLMProvider:
    cls = _REGISTRY.get((name or "").lower())
    if cls is None:
        raise GatewayError("INVALID_REQUEST", request_id, {"field": "provider", "allowed": sorted(_REGISTRY)})
    return cls()
