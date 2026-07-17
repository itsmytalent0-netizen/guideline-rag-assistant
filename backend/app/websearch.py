"""Web search: Tavily (1,000 free credits/mo) primary, DuckDuckGo fallback."""
import asyncio
import logging

import httpx

from .config import get_settings

settings = get_settings()
log = logging.getLogger(__name__)


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Returns [{title, url, snippet}]."""
    if settings.tavily_api_key:
        try:
            return await _tavily(query, max_results)
        except Exception as e:  # noqa: BLE001
            log.warning("Tavily failed (%s); falling back to DuckDuckGo", e)
    return await _ddg(query, max_results)


async def _tavily(query: str, max_results: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post("https://api.tavily.com/search", json={
            "api_key": settings.tavily_api_key,
            "query": query, "max_results": max_results,
            "search_depth": "basic", "include_answer": False,
        })
        r.raise_for_status()
        return [{"title": x.get("title", ""), "url": x.get("url", ""),
                 "snippet": x.get("content", "")[:1500]}
                for x in r.json().get("results", [])]


async def _ddg(query: str, max_results: int) -> list[dict]:
    def _sync():
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as d:
            return [{"title": x.get("title", ""),
                     "url": x.get("href", x.get("url", "")),
                     "snippet": x.get("body", "")[:1500]}
                    for x in d.text(query, max_results=max_results)]
    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:  # noqa: BLE001
        log.warning("DuckDuckGo search failed: %s", e)
        return []
