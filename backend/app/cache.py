"""Answer cache: DB-backed exact match + in-memory semantic match.

Guidelines users ask near-identical questions constantly; every cache hit is a
free-tier LLM request saved.
"""
import hashlib
import math

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .models import AnswerCache

settings = get_settings()

# in-memory: [(id, embedding, question_hash)]
_mem: list[tuple[int, list[float], str]] = []
_loaded = False


def _norm_key(question: str, mode: str, agency: str) -> str:
    base = f"{question.strip().lower()}|{mode}|{agency}"
    return hashlib.sha256(base.encode()).hexdigest()


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


async def _ensure_loaded(db: AsyncSession):
    global _loaded
    if _loaded:
        return
    res = await db.execute(select(AnswerCache.id, AnswerCache.embedding, AnswerCache.question_hash)
                           .order_by(AnswerCache.id.desc()).limit(settings.cache_max_entries))
    for cid, emb, qh in res.all():
        if emb:
            _mem.append((cid, emb, qh))
    _loaded = True


async def lookup(db: AsyncSession, question: str, mode: str, agency: str,
                 query_vector: list[float] | None) -> AnswerCache | None:
    await _ensure_loaded(db)
    # exact
    key = _norm_key(question, mode, agency)
    res = await db.execute(select(AnswerCache).where(AnswerCache.question_hash == key))
    hit = res.scalar_one_or_none()
    if hit:
        hit.hits += 1
        await db.commit()
        return hit
    # semantic
    if query_vector:
        best_id, best_sim = None, 0.0
        for cid, emb, _ in _mem:
            sim = _cos(query_vector, emb)
            if sim > best_sim:
                best_id, best_sim = cid, sim
        if best_id is not None and best_sim >= settings.semantic_cache_threshold:
            hit = await db.get(AnswerCache, best_id)
            if hit and hit.mode == mode:
                hit.hits += 1
                await db.commit()
                return hit
    return None


async def store(db: AsyncSession, question: str, mode: str, agency: str,
                answer: str, sources: list, model_used: str,
                query_vector: list[float] | None):
    key = _norm_key(question, mode, agency)
    res = await db.execute(select(AnswerCache).where(AnswerCache.question_hash == key))
    if res.scalar_one_or_none():
        return
    entry = AnswerCache(question_hash=key, question=question[:2000], mode=mode,
                        answer=answer, sources=sources, model_used=model_used,
                        embedding=query_vector or [])
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    if query_vector:
        _mem.append((entry.id, query_vector, key))
        if len(_mem) > settings.cache_max_entries:
            _mem.pop(0)


async def clear(db: AsyncSession):
    global _mem, _loaded
    await db.execute(delete(AnswerCache))
    await db.commit()
    _mem, _loaded = [], True
