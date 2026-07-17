"""Query orchestration: route (docs/web/both) → retrieve → synthesize with citations.

Deliberately lean — one LLM call per question — so free-tier rate limits go to
answering users, not to internal agent chatter.
"""
import asyncio
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .llm.router import stream_chat
from .models import ModelEntry
from .websearch import web_search

settings = get_settings()

WEB_HINTS = re.compile(
    r"\b(latest|news|recent|today|yesterday|this (week|month|year)|current|"
    r"upcoming|202[4-9]|breaking|announce|just (released|published))\b", re.I)

SYSTEM_PROMPT = """You are a pharmaceutical regulatory affairs assistant. Answer using ONLY the numbered sources provided. Never use outside knowledge or assumptions.

NON-NEGOTIABLE RULES:

1. ALWAYS CITE. Every factual sentence must end with the source number(s) that support it, e.g. [1] or [2][3]. A claim with no citation is not allowed — if you cannot attach a citation, do not make the claim.

2. SEGREGATE GUIDELINES FROM WEB. Sources marked (Guideline) are the internal master-data library; sources marked (Web) are live internet results. Structure every answer under clear headings when both are present:
   ## From the Guideline Library
   ...guideline-based answer with [n] citations...
   ## From the Web
   ...web-based answer with [n] citations...
   If only one kind of source is present, use only that heading. Never blend a guideline fact and a web fact into the same sentence.

3. DECLARE UNCERTAINTY. If the sources do not fully answer the question, state this explicitly. Begin such answers with "⚠️ Not fully covered by the available sources:" and then give only what the sources do support. Never fill gaps with invented regulatory content, numbers, clause references, or dates. If nothing relevant is found, say so plainly and stop.

4. BE PRECISE. Quote exact wording for critical requirements. Give exact clause/section numbers, limits, and definitions as written in the source. Do not paraphrase requirements loosely.

5. NEVER FABRICATE CITATIONS. Only cite source numbers that actually appear in the provided list. Do not invent [n] markers.

Write in clear, professional prose."""


async def get_active_models(db: AsyncSession) -> dict[str, list[str]]:
    """provider -> ordered list of active model ids (from admin-managed registry)."""
    res = await db.execute(select(ModelEntry).where(ModelEntry.is_active == True)  # noqa: E712
                           .order_by(ModelEntry.id))
    out: dict[str, list[str]] = {}
    for m in res.scalars():
        out.setdefault(m.provider, []).append(m.model_id)
    return out


def decide_mode(question: str, requested: str) -> str:
    """docs | web | both. Explicit user choice always wins."""
    if requested in ("docs", "web", "both"):
        return requested
    return "both" if WEB_HINTS.search(question) else "docs"


async def retrieve_docs(question: str, query_vector: list[float],
                        top_k: int, agency: str) -> list[dict]:
    from .rag import vectorstore
    try:
        hits = await asyncio.to_thread(vectorstore.search, question, query_vector,
                                       top_k, agency)
    except Exception:  # noqa: BLE001 — vector store not configured/reachable
        return []
    return [h for h in hits if h["score"] >= settings.retrieval_score_threshold] or hits[:3]


def build_sources(doc_hits: list[dict], web_hits: list[dict]) -> tuple[list[dict], str]:
    """Numbered source list (for UI + citations) and the context block for the LLM."""
    sources, blocks, n = [], [], 0
    budget = settings.max_context_chars
    for h in doc_hits:
        n += 1
        pages = f"p.{h['page_start']}" if h["page_start"] == h["page_end"] \
            else f"pp.{h['page_start']}-{h['page_end']}"
        label = f"{h['doc_name']} ({pages})"
        drive_url = (f"https://drive.google.com/file/d/{h['doc_id']}/view"
                     if h.get("doc_id") else "")
        sources.append({"n": n, "kind": "doc", "title": label, "doc_id": h["doc_id"],
                        "agency": h.get("agency", ""), "year": h.get("year", 0),
                        "pages": pages, "page_start": h.get("page_start", 0),
                        "url": drive_url})
        blocks.append(f"[{n}] (Guideline) {label}\n{h['text']}")
    for w in web_hits:
        n += 1
        sources.append({"n": n, "kind": "web", "title": w["title"], "url": w["url"],
                        "doc_id": "", "agency": "", "year": 0, "pages": ""})
        blocks.append(f"[{n}] (Web) {w['title']} — {w['url']}\n{w['snippet']}")

    context, used = [], 0
    for b in blocks:
        if used + len(b) > budget:
            break
        context.append(b)
        used += len(b)
    return sources, "\n\n---\n\n".join(context)


async def answer_stream(db: AsyncSession, question: str, mode_req: str,
                        pinned_model: str, agency: str, top_k: int,
                        history: list[dict] | None = None):
    """Async generator of SSE-ready events:
    ('mode', str) ('sources', list) ('model', str) ('delta', str) ('error', str)
    """
    from . import cache

    mode = decide_mode(question, mode_req)
    yield ("mode", mode)

    top_k = top_k or settings.retrieval_top_k

    query_vector = None
    doc_hits: list[dict] = []
    web_hits: list[dict] = []

    if mode in ("docs", "both"):
        from .rag.embeddings import embed_query
        query_vector = await asyncio.to_thread(embed_query, question)

    # cache check (exact + semantic) — a hit costs zero LLM quota
    if not history:  # only cache first-turn questions; follow-ups are contextual
        hit = await cache.lookup(db, question, mode_req, agency, query_vector)
        if hit:
            yield ("sources", hit.sources)
            yield ("model", hit.model_used + " (cached)")
            yield ("delta", hit.answer)
            return

    if mode in ("docs", "both"):
        doc_hits = await retrieve_docs(question, query_vector, top_k, agency)
        # auto mode: corpus came up empty -> pull in the web
        if mode == "docs" and mode_req == "auto" and not doc_hits:
            mode = "both"
    if mode in ("web", "both"):
        web_hits = await web_search(question, max_results=5)

    sources, context = build_sources(doc_hits, web_hits)
    yield ("sources", sources)

    if not context:
        yield ("delta", "I couldn't find anything relevant in the guideline library"
                        + ("" if mode == "docs" else " or on the web")
                        + ". Try rephrasing, or ask your admin whether this topic has been ingested.")
        yield ("model", "none")
        return

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in (history or [])[-6:]:
        messages.append({"role": h["role"], "content": h["content"][:2000]})
    messages.append({"role": "user",
                     "content": f"Sources:\n\n{context}\n\nQuestion: {question}"})

    active = await get_active_models(db)
    answer_parts: list[str] = []
    model_used = ""
    try:
        async for kind, val in stream_chat(messages, pinned_model, active):
            if kind == "model":
                model_used = val
            elif kind == "delta":
                answer_parts.append(val)
            yield (kind, val)
    except RuntimeError as e:
        yield ("error", str(e))
        return

    if answer_parts and not history:
        await cache.store(db, question, mode_req, agency, "".join(answer_parts),
                          sources, model_used, query_vector)
