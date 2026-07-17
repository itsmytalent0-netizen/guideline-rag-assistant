#!/usr/bin/env python3
"""Bulk ingestion CLI — runs on your Mac (M1: embeddings use the GPU via MPS).

Checkpointed and resumable: every file's status lives in the shared metadata DB
(Supabase), so you can stop anytime (Ctrl-C) and re-run later — it skips
everything already indexed. Spread the 500k pages over as many days as you like.

Usage (from the pharma-rag-web/ directory):
  python -m ingest.ingest --list            # show drives + progress
  python -m ingest.ingest --sync-manifest   # scan Drive, register files (fast)
  python -m ingest.ingest --run             # process pending files (resumable)
  python -m ingest.ingest --run --limit 200 # tonight's batch: 200 files
  python -m ingest.ingest --run --drive 1   # one drive only
  python -m ingest.ingest --retry-errors    # re-queue failed files

Config comes from the same .env as the server (DATABASE_URL, ZILLIZ_URI,
ZILLIZ_TOKEN, GOOGLE_SERVICE_ACCOUNT_JSON).
"""
import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone

from sqlalchemy import func, select

# reuse the server's modules — single source of truth
from backend.app.db import SessionLocal
from backend.app.drivesync import (download_file, get_drive_service,
                                   list_files_recursive)
from backend.app.models import Document, Drive
from backend.app.rag.chunking import build_rows, chunk_pages
from backend.app.rag.parsing import guess_metadata, looks_scanned, parse_file


async def sync_manifest():
    """Scan all active drives and register files in the manifest (no downloads)."""
    service = get_drive_service()
    async with SessionLocal() as db:
        drives = (await db.execute(select(Drive).where(Drive.is_active == True))).scalars().all()  # noqa: E712
        if not drives:
            print("No drives configured. Add one in the web admin panel first "
                  "(or insert into the drives table).")
            return
        for drive in drives:
            print(f"Scanning '{drive.name}' ({drive.folder_id}) …")
            files = list_files_recursive(service, drive.folder_id)
            print(f"  {len(files)} supported files found")
            res = await db.execute(select(Document).where(Document.drive_id == drive.id))
            existing = {d.gfile_id: d for d in res.scalars()}
            new = changed = 0
            for f in files:
                doc = existing.get(f["id"])
                if doc is None:
                    db.add(Document(drive_id=drive.id, gfile_id=f["id"], name=f["name"],
                                    mime_type=f["mimeType"],
                                    file_size=int(f.get("size", 0) or 0),
                                    md5=f.get("md5Checksum", ""),
                                    modified_time=f.get("modifiedTime", "")))
                    new += 1
                elif (doc.md5 != f.get("md5Checksum", "")
                      or doc.modified_time != f.get("modifiedTime", "")):
                    doc.md5 = f.get("md5Checksum", "")
                    doc.modified_time = f.get("modifiedTime", "")
                    doc.status = "pending"
                    changed += 1
            await db.commit()
            print(f"  manifest: +{new} new, {changed} changed -> pending")


async def run(limit: int, drive_id: int | None, use_ocr: bool):
    from backend.app.rag import vectorstore
    from backend.app.rag.embeddings import embed_passages, get_model

    print("Loading embedding model …")
    get_model()  # warm up (downloads on first run)
    vectorstore.ensure_collection()
    service = get_drive_service()

    async with SessionLocal() as db:
        statuses = ["pending", "needs_ocr"] if use_ocr else ["pending"]
        q = select(Document).where(Document.status.in_(statuses))
        if drive_id:
            q = q.where(Document.drive_id == drive_id)
        if limit:
            q = q.limit(limit)
        docs = (await db.execute(q)).scalars().all()
        drives = {d.id: d for d in (await db.execute(select(Drive))).scalars()}

        total = len(docs)
        print(f"{total} pending files to process. Ctrl-C anytime — progress is saved.\n")
        t0, done_pages, done_chunks = time.time(), 0, 0

        for i, doc in enumerate(docs, 1):
            label = f"[{i}/{total}] {doc.name[:70]}"
            try:
                data = download_file(service, doc.gfile_id)
                pages = parse_file(data, doc.mime_type, doc.name)

                if doc.mime_type == "application/pdf" and looks_scanned(pages):
                    if use_ocr:
                        pages = ocr_pdf(data)
                    else:
                        doc.status = "needs_ocr"
                        await db.commit()
                        print(f"{label} -> needs OCR (rerun with --ocr)")
                        continue

                drive = drives.get(doc.drive_id)
                meta = guess_metadata(doc.name, pages[0] if pages else "",
                                      drive.default_agency if drive else "")
                chunks = chunk_pages(pages)
                if not chunks:
                    doc.status, doc.error = "error", "no text extracted"
                    await db.commit()
                    print(f"{label} -> no text")
                    continue

                vectors = embed_passages([c.text for c in chunks], batch_size=256)
                vectorstore.delete_document(doc.gfile_id)
                rows = build_rows(doc.gfile_id, doc.name, doc.drive_id, chunks,
                                  vectors, meta["agency"], meta["year"])
                vectorstore.upsert_chunks(rows)

                doc.status = "indexed"
                doc.pages, doc.chunk_count, doc.error = len(pages), len(chunks), ""
                doc.indexed_at = datetime.now(timezone.utc)
                await db.commit()
                done_pages += len(pages)
                done_chunks += len(chunks)
                rate = done_pages / max(time.time() - t0, 1)
                print(f"{label} -> {len(pages)}p / {len(chunks)}ch  ({rate:.0f} pages/s)")

            except KeyboardInterrupt:
                print("\nInterrupted — progress saved. Re-run --run to resume.")
                return
            except Exception as e:  # noqa: BLE001
                doc.status, doc.error = "error", str(e)[:1000]
                await db.commit()
                print(f"{label} -> ERROR: {e}")

        print(f"\nDone. {done_pages} pages, {done_chunks} chunks in "
              f"{(time.time() - t0) / 60:.1f} min.")


def ocr_pdf(data: bytes) -> list[str]:
    """OCR an image-only PDF via ocrmypdf (brew install ocrmypdf)."""
    import subprocess
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf") as fin, \
         tempfile.NamedTemporaryFile(suffix=".pdf") as fout:
        fin.write(data)
        fin.flush()
        subprocess.run(["ocrmypdf", "--skip-text", "--quiet", fin.name, fout.name],
                       check=True)
        return parse_file(fout.name, "application/pdf")


async def show_status():
    async with SessionLocal() as db:
        drives = (await db.execute(select(Drive))).scalars().all()
        print(f"{'Drive':30} {'total':>7} {'indexed':>8} {'pending':>8} "
              f"{'ocr':>5} {'error':>6} {'pages':>9} {'chunks':>9}")
        for d in drives:
            async def cnt(status=None):
                q = select(func.count(Document.id)).where(Document.drive_id == d.id)
                if status:
                    q = q.where(Document.status == status)
                return (await db.execute(q)).scalar() or 0
            pages = (await db.execute(select(func.coalesce(func.sum(Document.pages), 0))
                                      .where(Document.drive_id == d.id))).scalar()
            chunks = (await db.execute(select(func.coalesce(func.sum(Document.chunk_count), 0))
                                       .where(Document.drive_id == d.id))).scalar()
            print(f"{d.name[:30]:30} {await cnt():>7} {await cnt('indexed'):>8} "
                  f"{await cnt('pending'):>8} {await cnt('needs_ocr'):>5} "
                  f"{await cnt('error'):>6} {pages:>9} {chunks:>9}")


async def retry_errors():
    from sqlalchemy import update
    async with SessionLocal() as db:
        res = await db.execute(update(Document).where(Document.status == "error")
                               .values(status="pending", error=""))
        await db.commit()
        print(f"Re-queued {res.rowcount} failed files.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="show drives + progress")
    ap.add_argument("--sync-manifest", action="store_true", help="scan Drive, register files")
    ap.add_argument("--run", action="store_true", help="process pending files")
    ap.add_argument("--limit", type=int, default=0, help="max files this run (0=all)")
    ap.add_argument("--drive", type=int, default=None, help="restrict to one drive id")
    ap.add_argument("--ocr", action="store_true", help="OCR scanned PDFs (needs ocrmypdf)")
    ap.add_argument("--retry-errors", action="store_true", help="re-queue failed files")
    args = ap.parse_args()

    if args.list:
        asyncio.run(show_status())
    elif args.sync_manifest:
        asyncio.run(sync_manifest())
    elif args.retry_errors:
        asyncio.run(retry_errors())
    elif args.run:
        asyncio.run(run(args.limit, args.drive, args.ocr))
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
