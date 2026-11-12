"""All config from environment variables (see .env.example). Secrets never leave the backend."""
import os

try:  # optional
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


MAX_INPUT_CHARS = int(env("MAX_INPUT_CHARS", "20000"))
LLM_TIMEOUT_S = float(env("LLM_TIMEOUT_S", "30"))
AUDIT_DB_PATH = env("AUDIT_DB_PATH", "audit.db")
DEFAULT_PROVIDER = env("DEFAULT_PROVIDER", "gemini")
LLM_FALLBACK = env("LLM_FALLBACK", "")          # "", "ollama" or "mock"
GEMINI_API_KEY = env("GEMINI_API_KEY")
GEMINI_MODEL = env("GEMINI_MODEL", "gemini-2.5-flash")  # VERIFY with the curl smoke test in the guide
OLLAMA_URL = env("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = env("OLLAMA_MODEL", "llama3.2:3b")
CORS_ORIGINS = [o for o in env("CORS_ORIGINS", "http://localhost:5173").split(",") if o]
