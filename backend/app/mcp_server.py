"""MCP server (Phase 8) — lets Claude Desktop / any MCP client query the corpus.

Mounted at /mcp (streamable HTTP). Auth: X-API-Key header, validated against
the users table (each user has an API key on their profile page).

Tools: search_guidelines, ask_guidelines, list_documents.
"""
import asyncio
import logging

log = logging.getLogger(__name__)


def build_mcp_app():
    """Returns an ASGI app to mount, or None if fastmcp isn't installed."""
    try:
        from fastmcp import FastMCP
        from fastmcp.server.dependencies import get_http_request
    except ImportError:
        log.info("fastmcp not installed — MCP endpoint disabled")
        return None

    from sqlalchemy import select

    from .db import SessionLocal
    from .models import User

    mcp = FastMCP("pharma-guidelines-rag")

    async def _auth() -> User:
        request = get_http_request()
        api_key = request.headers.get("X-API-Key", "")
        async with SessionLocal() as db:
            res = await db.execute(select(User).where(User.api_key == api_key))
            user = res.scalar_one_or_none()
        if not user or not user.is_active:
            raise PermissionError("Invalid or missing X-API-Key header")
        return user

    @mcp.tool
    async def search_guidelines(query: str, top_k: int = 8, agency: str = "") -> list[dict]:
        """Search the pharmaceutical guideline library. Returns matching chunks
        with document name, agency, page range and text.

        Args:
            query: what to search for
            top_k: number of results (1-20)
            agency: optional filter, e.g. FDA, EMA, ICH, WHO
        """
        await _auth()
        from .rag import vectorstore
        from .rag.embeddings import embed_query
        vec = await asyncio.to_thread(embed_query, query)
        hits = await asyncio.to_thread(vectorstore.search, query, vec,
                                       max(1, min(top_k, 20)), agency)
        return [{"doc_name": h["doc_name"], "agency": h["agency"],
                 "pages": f"{h['page_start']}-{h['page_end']}",
                 "score": round(h["score"], 4), "text": h["text"]} for h in hits]

    @mcp.tool
    async def ask_guidelines(question: str, agency: str = "") -> dict:
        """Ask a question and get a synthesized, cited answer from the
        pharmaceutical guideline library.

        Args:
            question: the question to answer
            agency: optional filter, e.g. FDA, EMA, ICH, WHO
        """
        await _auth()
        from .orchestrator import answer_stream
        async with SessionLocal() as db:
            answer_parts, sources = [], []
            async for kind, val in answer_stream(db, question, "docs", "auto",
                                                 agency, 0, None):
                if kind == "delta":
                    answer_parts.append(val)
                elif kind == "sources":
                    sources = val
                elif kind == "error":
                    return {"error": val}
        return {"answer": "".join(answer_parts),
                "sources": [{"n": s["n"], "title": s["title"]} for s in sources]}

    @mcp.tool
    async def list_documents(limit: int = 50) -> list[dict]:
        """List indexed guideline documents (name, pages, chunk count)."""
        await _auth()
        from .models import Document
        async with SessionLocal() as db:
            res = await db.execute(select(Document).where(Document.status == "indexed")
                                   .order_by(Document.name).limit(max(1, min(limit, 500))))
            return [{"name": d.name, "pages": d.pages, "chunks": d.chunk_count}
                    for d in res.scalars()]

    return mcp.http_app(path="/")
