"""Admin endpoints: drives, sync jobs, model registry refresh, users, stats."""
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import cache
from .db import get_db
from .llm.providers import get_providers
from .llm.router import provider_status
from .models import (AuditLog, ChatSession, Document, Drive, Message,
                     ModelEntry, SyncJob, User)
from .schemas import DriveIn, ModelToggleIn, UserUpdateIn
from .security import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_admin)])
log = logging.getLogger(__name__)


# ---------- Drives ----------

@router.get("/drives")
async def list_drives(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Drive).order_by(Drive.id))
    return [{"id": d.id, "name": d.name, "folder_id": d.folder_id,
             "default_agency": d.default_agency, "is_active": d.is_active,
             "last_synced": str(d.last_synced) if d.last_synced else None}
            for d in res.scalars()]


@router.post("/drives")
async def add_drive(body: DriveIn, db: AsyncSession = Depends(get_db),
                    admin: User = Depends(require_admin)):
    d = Drive(name=body.name, folder_id=body.folder_id,
              default_agency=body.default_agency, created_by=admin.id)
    db.add(d)
    db.add(AuditLog(user_id=admin.id, action="add_drive", detail={"name": body.name}))
    await db.commit()
    return {"id": d.id}


@router.patch("/drives/{drive_id}")
async def toggle_drive(drive_id: int, db: AsyncSession = Depends(get_db)):
    d = await db.get(Drive, drive_id)
    if not d:
        raise HTTPException(404, "Drive not found")
    d.is_active = not d.is_active
    await db.commit()
    return {"id": d.id, "is_active": d.is_active}


@router.delete("/drives/{drive_id}")
async def delete_drive(drive_id: int, db: AsyncSession = Depends(get_db)):
    d = await db.get(Drive, drive_id)
    if not d:
        raise HTTPException(404, "Drive not found")
    await db.delete(d)
    await db.commit()
    return {"ok": True}


# ---------- Sync ----------

@router.post("/sync")
async def trigger_sync(background: BackgroundTasks, db: AsyncSession = Depends(get_db),
                       admin: User = Depends(require_admin)):
    running = await db.execute(select(SyncJob).where(SyncJob.status == "running"))
    if running.scalar_one_or_none():
        raise HTTPException(409, "A sync is already running")
    job = SyncJob(job_type="delta")
    db.add(job)
    db.add(AuditLog(user_id=admin.id, action="trigger_sync"))
    await db.commit()
    await db.refresh(job)

    from .drivesync import run_delta_sync
    background.add_task(run_delta_sync, job.id)
    return {"job_id": job.id}


@router.get("/sync/jobs")
async def list_jobs(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(SyncJob).order_by(SyncJob.id.desc()).limit(20))
    return [{"id": j.id, "type": j.job_type, "status": j.status, "stats": j.stats,
             "started_at": str(j.started_at),
             "finished_at": str(j.finished_at) if j.finished_at else None}
            for j in res.scalars()]


@router.get("/sync/jobs/{job_id}")
async def job_detail(job_id: int, db: AsyncSession = Depends(get_db)):
    j = await db.get(SyncJob, job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    return {"id": j.id, "type": j.job_type, "status": j.status, "stats": j.stats,
            "log": j.log, "started_at": str(j.started_at),
            "finished_at": str(j.finished_at) if j.finished_at else None}


# ---------- Model registry ----------

@router.post("/models/refresh")
async def refresh_models(db: AsyncSession = Depends(get_db)):
    """Query every configured provider's live model-list API and upsert the
    registry. New free models become selectable immediately."""
    providers = get_providers()
    results, added, updated = {}, 0, 0
    for name, p in providers.items():
        if not p.configured:
            results[name] = "not configured"
            continue
        try:
            models = await p.list_models()
        except Exception as e:  # noqa: BLE001
            results[name] = f"error: {e}"
            log.warning("Model refresh failed for %s: %s", name, e)
            continue
        for m in models:
            res = await db.execute(select(ModelEntry).where(
                ModelEntry.provider == name, ModelEntry.model_id == m["model_id"]))
            row = res.scalar_one_or_none()
            if row:
                row.display_name = m["display_name"]
                row.context_length = m["context_length"] or row.context_length
                row.fetched_at = datetime.now(timezone.utc)
                updated += 1
            else:
                # NVIDIA's catalog is huge — imported inactive for admin curation
                db.add(ModelEntry(provider=name, model_id=m["model_id"],
                                  display_name=m["display_name"],
                                  context_length=m["context_length"] or 0,
                                  is_active=(name != "nvidia")))
                added += 1
        results[name] = f"{len(models)} models"
    await db.commit()
    return {"added": added, "updated": updated, "providers": results}


@router.get("/models")
async def all_models(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(ModelEntry).order_by(ModelEntry.provider, ModelEntry.model_id))
    return [{"id": m.id, "provider": m.provider, "model_id": m.model_id,
             "display_name": m.display_name, "context_length": m.context_length,
             "is_active": m.is_active, "fetched_at": str(m.fetched_at)}
            for m in res.scalars()]


@router.patch("/models/{model_pk}")
async def toggle_model(model_pk: int, body: ModelToggleIn,
                       db: AsyncSession = Depends(get_db)):
    m = await db.get(ModelEntry, model_pk)
    if not m:
        raise HTTPException(404, "Model not found")
    m.is_active = body.is_active
    await db.commit()
    return {"id": m.id, "is_active": m.is_active}


# ---------- Users ----------

@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).order_by(User.id))
    return [{"id": u.id, "email": u.email, "role": u.role, "is_active": u.is_active,
             "created_at": str(u.created_at)} for u in res.scalars()]


@router.patch("/users/{user_id}")
async def update_user(user_id: int, body: UserUpdateIn,
                      db: AsyncSession = Depends(get_db),
                      admin: User = Depends(require_admin)):
    u = await db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id and body.role == "user":
        raise HTTPException(400, "You cannot demote yourself")
    if body.role in ("user", "admin"):
        u.role = body.role
    if body.is_active is not None:
        u.is_active = body.is_active
    await db.commit()
    return {"id": u.id, "role": u.role, "is_active": u.is_active}


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db),
                      admin: User = Depends(require_admin)):
    u = await db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id:
        raise HTTPException(400, "You cannot delete your own account")
    # remove the user's chat data first (sessions -> messages)
    sessions = await db.execute(select(ChatSession.id).where(ChatSession.user_id == user_id))
    session_ids = [s for (s,) in sessions.all()]
    if session_ids:
        await db.execute(delete(Message).where(Message.session_id.in_(session_ids)))
        await db.execute(delete(ChatSession).where(ChatSession.user_id == user_id))
    db.add(AuditLog(user_id=admin.id, action="delete_user",
                    detail={"deleted_email": u.email}))
    await db.delete(u)
    await db.commit()
    return {"ok": True, "deleted": u.email}


# ---------- Stats / status ----------

@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    docs_total = (await db.execute(select(func.count(Document.id)))).scalar() or 0
    docs_indexed = (await db.execute(select(func.count(Document.id))
                                     .where(Document.status == "indexed"))).scalar() or 0
    docs_ocr = (await db.execute(select(func.count(Document.id))
                                 .where(Document.status == "needs_ocr"))).scalar() or 0
    docs_err = (await db.execute(select(func.count(Document.id))
                                 .where(Document.status == "error"))).scalar() or 0
    pages = (await db.execute(select(func.coalesce(func.sum(Document.pages), 0)))).scalar() or 0
    chunks = (await db.execute(select(func.coalesce(func.sum(Document.chunk_count), 0)))).scalar() or 0
    users = (await db.execute(select(func.count(User.id)))).scalar() or 0

    from .rag import vectorstore
    vstats = await asyncio.to_thread(vectorstore.collection_stats)

    return {"documents": {"total": docs_total, "indexed": docs_indexed,
                          "needs_ocr": docs_ocr, "errors": docs_err},
            "pages": int(pages), "chunks": int(chunks), "users": users,
            "vector_store": vstats, "providers": provider_status()}


@router.get("/documents")
async def list_documents(status: str = "", limit: int = 100, offset: int = 0,
                         db: AsyncSession = Depends(get_db)):
    q = select(Document).order_by(Document.id.desc()).limit(min(limit, 500)).offset(offset)
    if status:
        q = q.where(Document.status == status)
    res = await db.execute(q)
    return [{"id": d.id, "name": d.name, "status": d.status, "pages": d.pages,
             "chunks": d.chunk_count, "error": d.error[:200],
             "indexed_at": str(d.indexed_at) if d.indexed_at else None}
            for d in res.scalars()]


@router.post("/cache/clear")
async def clear_cache(db: AsyncSession = Depends(get_db)):
    await cache.clear(db)
    return {"ok": True}
