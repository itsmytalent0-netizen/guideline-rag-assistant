"""On-demand reference-page rendering.

Given a document (Drive file id) and page number, fetch the PDF from Google
Drive and render just that page to a PNG. Works with already-ingested data
(doc_id + page are stored on every chunk). Small in-memory caches keep the
free instance responsive without persisting anything.
"""
import asyncio
import io
import logging
from collections import OrderedDict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from .models import User
from .security import get_current_user

router = APIRouter(prefix="/api", tags=["pages"])
log = logging.getLogger(__name__)

# tiny LRU caches (bounded so 512 MB RAM is safe)
_pdf_cache: "OrderedDict[str, bytes]" = OrderedDict()   # doc_id -> pdf bytes
_png_cache: "OrderedDict[str, bytes]" = OrderedDict()    # doc_id:page -> png
_PDF_MAX = 3
_PNG_MAX = 40


def _cache_get(cache, key):
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    return None


def _cache_put(cache, key, val, limit):
    cache[key] = val
    cache.move_to_end(key)
    while len(cache) > limit:
        cache.popitem(last=False)


def _render_page(pdf_bytes: bytes, page: int) -> bytes:
    import fitz  # PyMuPDF
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        if page < 1 or page > doc.page_count:
            page = max(1, min(page, doc.page_count))
        pix = doc[page - 1].get_pixmap(dpi=120)
        return pix.tobytes("png")


def _fetch_and_render(doc_id: str, page: int) -> bytes:
    from .drivesync import download_file, get_drive_service
    pdf = _cache_get(_pdf_cache, doc_id)
    if pdf is None:
        service = get_drive_service()
        pdf = download_file(service, doc_id)
        _cache_put(_pdf_cache, doc_id, pdf, _PDF_MAX)
    return _render_page(pdf, page)


@router.get("/page-image/{doc_id}/{page}")
async def page_image(doc_id: str, page: int, user: User = Depends(get_current_user)):
    """Return the rendered reference page as PNG (any logged-in user)."""
    key = f"{doc_id}:{page}"
    png = _cache_get(_png_cache, key)
    if png is None:
        try:
            png = await asyncio.to_thread(_fetch_and_render, doc_id, page)
        except Exception as e:  # noqa: BLE001
            log.warning("page render failed for %s p.%s: %s", doc_id, page, e)
            raise HTTPException(404, "Could not render that page (non-PDF, "
                                     "scanned image, or file unavailable).")
        _cache_put(_png_cache, key, png, _PNG_MAX)
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=3600"})
