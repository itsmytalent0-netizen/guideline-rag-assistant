"""Public metadata endpoints: health, model list for the chat dropdown."""
from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import ModelEntry, User
from .security import get_current_user

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/health/db")
async def health_db(db: AsyncSession = Depends(get_db)):
    """Also used by the keep-alive cron: issues a real query so Supabase
    never pauses for inactivity."""
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "ok"}


@router.get("/models")
async def list_models(user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    """Active models for the user-facing dropdown ('Auto' is added client-side)."""
    res = await db.execute(select(ModelEntry).where(ModelEntry.is_active == True)  # noqa: E712
                           .order_by(ModelEntry.provider, ModelEntry.model_id))
    return [{"value": f"{m.provider}/{m.model_id}",
             "label": f"{m.display_name or m.model_id} ({m.provider})",
             "provider": m.provider, "context_length": m.context_length}
            for m in res.scalars()]
