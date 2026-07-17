"""Google Drive access + server-side DELTA sync.

Bulk ingestion of the full corpus runs on the admin's machine via `ingest/`
(free server can't do 500k pages). This module handles the ongoing case:
admin drops a few new/updated guidelines into Drive and clicks "Sync".
"""
import asyncio
import base64
import io
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal
from .models import Document, Drive, SyncJob

settings = get_settings()
log = logging.getLogger(__name__)

SUPPORTED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


def load_service_account() -> dict:
    raw = settings.google_service_account_json
    if not raw:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON not configured")
    raw = raw.strip()
    if not raw.startswith("{"):
        raw = base64.b64decode(raw).decode()
    return json.loads(raw)


def get_drive_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_info(
        load_service_account(), scopes=["https://www.googleapis.com/auth/drive.readonly"])
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def list_files_recursive(service, folder_id: str) -> list[dict]:
    """All supported files under a folder (walks subfolders)."""
    files, queue = [], [folder_id]
    while queue:
        fid = queue.pop()
        page_token = None
        while True:
            resp = service.files().list(
                q=f"'{fid}' in parents and trashed=false",
                fields="nextPageToken, files(id,name,mimeType,size,md5Checksum,modifiedTime)",
                pageSize=1000, pageToken=page_token,
                supportsAllDrives=True, includeItemsFromAllDrives=True,
            ).execute()
            for f in resp.get("files", []):
                if f["mimeType"] == "application/vnd.google-apps.folder":
                    queue.append(f["id"])
                elif f["mimeType"] in SUPPORTED_MIMES:
                    files.append(f)
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    return files


def download_file(service, file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, service.files().get_media(
        fileId=file_id, supportsAllDrives=True))
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def _process_file_sync(service, f: dict, drive_row_id: int, default_agency: str) -> dict:
    """Blocking: download → parse → chunk → embed → upsert. Returns result info."""
    from .rag import vectorstore
    from .rag.chunking import build_rows, chunk_pages
    from .rag.embeddings import embed_passages
    from .rag.parsing import guess_metadata, looks_scanned, parse_file

    data = download_file(service, f["id"])
    pages = parse_file(data, f["mimeType"], f["name"])
    if f["mimeType"] == "application/pdf" and looks_scanned(pages):
        return {"status": "needs_ocr", "pages": len(pages), "chunks": 0}

    meta = guess_metadata(f["name"], pages[0] if pages else "", default_agency)
    chunks = chunk_pages(pages)
    if not chunks:
        return {"status": "error", "error": "no text extracted", "pages": len(pages), "chunks": 0}

    vectorstore.delete_document(f["id"])  # replace any previous version
    vectors = embed_passages([c.text for c in chunks])
    rows = build_rows(f["id"], f["name"], drive_row_id, chunks, vectors,
                      meta["agency"], meta["year"])
    vectorstore.upsert_chunks(rows)
    return {"status": "indexed", "pages": len(pages), "chunks": len(chunks),
            "agency": meta["agency"]}


async def run_delta_sync(job_id: int):
    """Background task: sync every active drive; only new/changed/deleted files."""
    async with SessionLocal() as db:
        job = await db.get(SyncJob, job_id)
        stats = {"scanned": 0, "new": 0, "updated": 0, "deleted": 0,
                 "needs_ocr": 0, "errors": 0}
        lines: list[str] = []

        def logline(msg: str):
            lines.append(msg)
            log.info("[sync %s] %s", job_id, msg)

        try:
            service = await asyncio.to_thread(get_drive_service)
            drives = (await db.execute(select(Drive).where(Drive.is_active == True)))  # noqa: E712
            for drive in drives.scalars().all():
                logline(f"Scanning drive '{drive.name}'…")
                files = await asyncio.to_thread(list_files_recursive, service, drive.folder_id)
                stats["scanned"] += len(files)
                seen_ids = {f["id"] for f in files}

                res = await db.execute(select(Document).where(Document.drive_id == drive.id))
                existing = {d.gfile_id: d for d in res.scalars()}

                for f in files:
                    doc = existing.get(f["id"])
                    changed = doc and (doc.md5 != f.get("md5Checksum", "")
                                       or doc.modified_time != f.get("modifiedTime", ""))
                    if doc and not changed and doc.status == "indexed":
                        continue
                    if doc is None:
                        doc = Document(drive_id=drive.id, gfile_id=f["id"], name=f["name"])
                        db.add(doc)
                        stats["new"] += 1
                    elif changed:
                        stats["updated"] += 1

                    doc.name = f["name"]
                    doc.mime_type = f["mimeType"]
                    doc.file_size = int(f.get("size", 0) or 0)
                    doc.md5 = f.get("md5Checksum", "")
                    doc.modified_time = f.get("modifiedTime", "")
                    try:
                        result = await asyncio.to_thread(
                            _process_file_sync, service, f, drive.id, drive.default_agency)
                        doc.status = result["status"]
                        doc.pages = result["pages"]
                        doc.chunk_count = result["chunks"]
                        doc.error = result.get("error", "")
                        if result["status"] == "indexed":
                            doc.indexed_at = datetime.now(timezone.utc)
                            logline(f"Indexed: {f['name']} ({result['chunks']} chunks)")
                        elif result["status"] == "needs_ocr":
                            stats["needs_ocr"] += 1
                            logline(f"Needs OCR (skipped): {f['name']}")
                        else:
                            stats["errors"] += 1
                            logline(f"Error: {f['name']}: {doc.error}")
                    except Exception as e:  # noqa: BLE001
                        doc.status = "error"
                        doc.error = str(e)[:1000]
                        stats["errors"] += 1
                        logline(f"Error: {f['name']}: {e}")
                    await db.commit()

                # deletions
                for gid, doc in existing.items():
                    if gid not in seen_ids and doc.status != "deleted":
                        from .rag import vectorstore
                        await asyncio.to_thread(vectorstore.delete_document, gid)
                        doc.status = "deleted"
                        doc.chunk_count = 0
                        stats["deleted"] += 1
                        logline(f"Removed (deleted in Drive): {doc.name}")
                drive.last_synced = datetime.now(timezone.utc)
                await db.commit()

            job.status = "done"
        except Exception as e:  # noqa: BLE001
            job.status = "error"
            lines.append(f"FATAL: {e}")
            log.exception("Delta sync failed")
        finally:
            job.stats = stats
            job.log = "\n".join(lines[-500:])
            job.finished_at = datetime.now(timezone.utc)
            await db.commit()
