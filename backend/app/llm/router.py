"""LLM router: provider rotation, rate-limit tracking, 429 cooldowns, streaming.

`stream_chat()` yields text deltas. In Auto mode it walks the priority list and
fails over transparently; a pinned "provider/model" is tried first, then Auto.
"""
import asyncio
import json
import logging
import time
from collections import deque

import httpx

from ..config import get_settings
from .providers import DEFAULT_MODELS, get_providers

settings = get_settings()
log = logging.getLogger(__name__)


class _Budget:
    """Sliding-window RPM + daily counter per provider, plus 429 cooldown."""

    def __init__(self, rpm: int, rpd: int):
        self.rpm, self.rpd = rpm, rpd
        self.minute: deque[float] = deque()
        self.day_count = 0
        self.day_start = time.time()
        self.cooldown_until = 0.0

    def allow(self) -> bool:
        now = time.time()
        if now < self.cooldown_until:
            return False
        if now - self.day_start > 86400:
            self.day_count, self.day_start = 0, now
        while self.minute and now - self.minute[0] > 60:
            self.minute.popleft()
        return len(self.minute) < self.rpm and self.day_count < self.rpd

    def record(self):
        self.minute.append(time.time())
        self.day_count += 1

    def punish(self, seconds: float = 90):
        self.cooldown_until = time.time() + seconds


_budgets: dict[str, _Budget] = {}


def _budget(name: str, rpm: int, rpd: int) -> _Budget:
    if name not in _budgets:
        _budgets[name] = _Budget(rpm, rpd)
    return _budgets[name]


def provider_status() -> list[dict]:
    out = []
    for name, p in get_providers().items():
        b = _budgets.get(name)
        out.append({
            "provider": name,
            "configured": p.configured,
            "used_today": b.day_count if b else 0,
            "daily_budget": p.rpd,
            "cooling_down": bool(b and time.time() < b.cooldown_until),
        })
    return out


def _candidates(pinned: str, active_models: dict[str, list[str]]) -> list[tuple[str, str]]:
    """Ordered (provider, model) candidates. `active_models`: provider -> model ids."""
    providers = get_providers()
    order = [x.strip() for x in settings.llm_priority.split(",") if x.strip()]
    cands: list[tuple[str, str]] = []

    if pinned and pinned != "auto" and "/" in pinned:
        prov, model = pinned.split("/", 1)
        if prov in providers:
            cands.append((prov, model))

    for prov in order:
        p = providers.get(prov)
        if not p or not p.configured:
            continue
        models = active_models.get(prov) or []
        model = models[0] if models else DEFAULT_MODELS.get(prov, "")
        if model and (prov, model) not in cands:
            cands.append((prov, model))
    return cands


async def stream_chat(messages: list[dict], pinned_model: str = "auto",
                      active_models: dict[str, list[str]] | None = None,
                      max_tokens: int = 1600, temperature: float = 0.2):
    """Async generator yielding ('model', name) once, then ('delta', text) events.

    Raises RuntimeError if every provider is exhausted.
    """
    providers = get_providers()
    cands = _candidates(pinned_model, active_models or {})
    if not cands:
        raise RuntimeError("No LLM provider configured. Add at least one API key.")

    errors = []
    for prov_name, model in cands:
        p = providers[prov_name]
        if not p.configured:
            continue
        b = _budget(prov_name, p.rpm, p.rpd)
        if not b.allow():
            errors.append(f"{prov_name}: rate budget exhausted")
            continue

        # Cerebras free tier caps context ~8K — skip if prompt is too large
        approx_tokens = sum(len(m["content"]) for m in messages) // 4
        if approx_tokens + max_tokens > p.max_context:
            errors.append(f"{prov_name}: context too small")
            continue

        b.record()
        try:
            got_any = False
            async for delta in _stream_openai(p, model, messages, max_tokens, temperature):
                if not got_any:
                    got_any = True
                    yield ("model", f"{prov_name}/{model}")
                yield ("delta", delta)
            if got_any:
                return
            errors.append(f"{prov_name}/{model}: empty response")
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code in (429, 503):
                b.punish(120)
            errors.append(f"{prov_name}/{model}: HTTP {code}")
            log.warning("Provider %s failed: HTTP %s", prov_name, code)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{prov_name}/{model}: {type(e).__name__}")
            log.warning("Provider %s failed: %s", prov_name, e)
        await asyncio.sleep(0)

    raise RuntimeError("All providers failed/exhausted: " + "; ".join(errors[-6:]))


async def _stream_openai(p, model: str, messages: list[dict],
                         max_tokens: int, temperature: float):
    payload = {"model": model, "messages": messages, "stream": True,
               "max_tokens": max_tokens, "temperature": temperature}
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15)) as client:
        async with client.stream("POST", f"{p.base_url}/chat/completions",
                                 headers=p.headers(), json=payload) as r:
            if r.status_code >= 400:
                await r.aread()
                raise httpx.HTTPStatusError("error", request=r.request, response=r)
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                    delta = obj["choices"][0].get("delta", {}).get("content")
                    if delta:
                        yield delta
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


async def complete(messages: list[dict], pinned_model: str = "auto",
                   active_models: dict[str, list[str]] | None = None,
                   max_tokens: int = 800) -> tuple[str, str]:
    """Non-streaming helper. Returns (text, model_used)."""
    parts, model_used = [], ""
    async for kind, val in stream_chat(messages, pinned_model, active_models, max_tokens):
        if kind == "model":
            model_used = val
        else:
            parts.append(val)
    return "".join(parts), model_used
