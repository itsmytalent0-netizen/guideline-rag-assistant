"""Free LLM provider registry.

Every provider exposes an OpenAI-compatible /chat/completions endpoint, so one
HTTP client serves them all. `list_models()` fetches each provider's live model
list (admin "Refresh models") — filtered to free models where the provider has
paid tiers (OpenRouter). New free models appear with a refresh, no code change.
"""
import httpx

from ..config import get_settings

settings = get_settings()


class Provider:
    def __init__(self, name: str, base_url: str, api_key: str,
                 rpm: int, rpd: int, max_context: int = 32768):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.rpm = rpm            # conservative requests/minute budget
        self.rpd = rpd            # conservative requests/day budget
        self.max_context = max_context

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def headers(self) -> dict:
        h = {"Authorization": f"Bearer {self.api_key}"}
        if self.name == "openrouter":
            h["HTTP-Referer"] = "https://huggingface.co"
            h["X-Title"] = settings.app_name
        return h

    async def list_models(self) -> list[dict]:
        """Return [{model_id, display_name, context_length}] of FREE chat models."""
        async with httpx.AsyncClient(timeout=30) as client:
            if self.name == "gemini":
                r = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"key": self.api_key, "pageSize": 200})
                r.raise_for_status()
                out = []
                for m in r.json().get("models", []):
                    if "generateContent" in m.get("supportedGenerationMethods", []):
                        mid = m["name"].removeprefix("models/")
                        if any(x in mid for x in ("embedding", "aqa", "image", "tts", "veo")):
                            continue
                        out.append({"model_id": mid,
                                    "display_name": m.get("displayName", mid),
                                    "context_length": m.get("inputTokenLimit", 0)})
                return out

            if self.name == "github":
                r = await client.get("https://models.github.ai/catalog/models",
                                     headers=self.headers())
                r.raise_for_status()
                return [{"model_id": m.get("id", ""),
                         "display_name": m.get("name", m.get("id", "")),
                         "context_length": (m.get("limits") or {}).get("max_input_tokens", 0)}
                        for m in r.json() if m.get("id")]

            # OpenAI-compatible /models for everyone else
            r = await client.get(f"{self.base_url}/models", headers=self.headers())
            r.raise_for_status()
            data = r.json().get("data", [])
            out = []
            for m in data:
                mid = m.get("id", "")
                if not mid:
                    continue
                if self.name == "openrouter":
                    pricing = m.get("pricing", {})
                    if float(pricing.get("prompt", 1) or 1) != 0 or \
                       float(pricing.get("completion", 1) or 1) != 0:
                        continue  # only truly free models
                if self.name == "groq" and any(x in mid for x in ("whisper", "tts", "guard")):
                    continue
                out.append({"model_id": mid,
                            "display_name": m.get("name", mid),
                            "context_length": m.get("context_length", 0)
                                              or m.get("context_window", 0)})
            return out


def get_providers() -> dict[str, Provider]:
    """All providers, keyed by name. Only `configured` ones are usable."""
    s = get_settings()
    return {
        "groq": Provider("groq", "https://api.groq.com/openai/v1", s.groq_api_key,
                         rpm=25, rpd=7000),
        "gemini": Provider("gemini",
                           "https://generativelanguage.googleapis.com/v1beta/openai",
                           s.gemini_api_key, rpm=8, rpd=1200),
        "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1",
                               s.openrouter_api_key, rpm=15, rpd=45),
        "mistral": Provider("mistral", "https://api.mistral.ai/v1", s.mistral_api_key,
                            rpm=30, rpd=5000),
        "nvidia": Provider("nvidia", "https://integrate.api.nvidia.com/v1",
                           s.nvidia_api_key, rpm=35, rpd=5000),
        "github": Provider("github", "https://models.github.ai/inference",
                           s.github_token, rpm=10, rpd=150),
        "cerebras": Provider("cerebras", "https://api.cerebras.ai/v1",
                             s.cerebras_api_key, rpm=25, rpd=1000, max_context=8192),
    }


# Sensible default model per provider, used by Auto mode before the first
# admin refresh has populated the registry.
DEFAULT_MODELS = {
    "groq": "llama-3.3-70b-versatile",
    "gemini": "gemini-2.0-flash",
    "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
    "mistral": "mistral-small-latest",
    "nvidia": "meta/llama-3.3-70b-instruct",
    "github": "openai/gpt-4o-mini",
    "cerebras": "llama-3.3-70b",
}
