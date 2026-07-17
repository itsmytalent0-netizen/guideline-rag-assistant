"""Chat endpoints: SSE streaming answers, session/history management."""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import AuditLog, ChatSession, Message, User
from .orchestrator import answer_stream
from .ratelimit import check_user_rate
from .schemas import ChatIn
from .security import get_current_user

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/ask")
async def ask(body: ChatIn, user: User = Depends(get_current_user),
              db: AsyncSession = Depends(get_db)):
    check_user_rate(user.id)

    # session handling
    if body.session_id:
        session = await db.get(ChatSession, body.session_id)
        if not session or session.user_id != user.id:
            raise HTTPException(404, "Session not found")
    else:
        session = ChatSession(user_id=user.id, title=body.question[:80])
        db.add(session)
        await db.commit()
        await db.refresh(session)

    res = await db.execute(select(Message).where(Message.session_id == session.id)
                           .order_by(Message.id))
    history = [{"role": m.role, "content": m.content} for m in res.scalars()]

    db.add(Message(session_id=session.id, role="user", content=body.question))
    db.add(AuditLog(user_id=user.id, action="ask",
                    detail={"q": body.question[:500], "mode": body.mode}))
    await db.commit()

    async def gen():
        yield _sse("session", {"session_id": session.id, "title": session.title})
        answer_parts, sources, model_used = [], [], ""
        try:
            async for kind, val in answer_stream(db, body.question, body.mode,
                                                 body.model, body.agency,
                                                 body.top_k, history):
                if kind == "delta":
                    answer_parts.append(val)
                elif kind == "sources":
                    sources = val
                elif kind == "model":
                    model_used = val
                yield _sse(kind, val)
        except Exception as e:  # noqa: BLE001
            yield _sse("error", f"Unexpected error: {e}")
        # persist assistant turn
        if answer_parts:
            db.add(Message(session_id=session.id, role="assistant",
                           content="".join(answer_parts), sources=sources,
                           model_used=model_used))
            await db.commit()
        yield _sse("done", {"model": model_used})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.get("/sessions")
async def list_sessions(user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(ChatSession).where(ChatSession.user_id == user.id)
                           .order_by(ChatSession.id.desc()).limit(50))
    return [{"id": s.id, "title": s.title, "created_at": str(s.created_at)}
            for s in res.scalars()]


@router.get("/sessions/{session_id}")
async def get_session(session_id: int, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    session = await db.get(ChatSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(404, "Session not found")
    res = await db.execute(select(Message).where(Message.session_id == session_id)
                           .order_by(Message.id))
    return {"id": session.id, "title": session.title,
            "messages": [{"role": m.role, "content": m.content, "sources": m.sources,
                          "model": m.model_used} for m in res.scalars()]}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: int, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    session = await db.get(ChatSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(404, "Session not found")
    await db.execute(delete(Message).where(Message.session_id == session_id))
    await db.delete(session)
    await db.commit()
    return {"ok": True}
