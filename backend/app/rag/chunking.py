"""Token-aware, page-tracking chunker. Shared by server and ingestion CLI.

~800 tokens per chunk (approximated as chars/4), 15% overlap, splits on
paragraph > sentence boundaries, and records the page range of each chunk.
"""
from dataclasses import dataclass, field

CHUNK_CHARS = 3200      # ~800 tokens
OVERLAP_CHARS = 480     # ~15%
MIN_CHUNK_CHARS = 200


@dataclass
class Chunk:
    text: str
    page_start: int
    page_end: int
    index: int = 0
    meta: dict = field(default_factory=dict)


def chunk_pages(pages: list[str]) -> list[Chunk]:
    """Split per-page texts into overlapping chunks with page ranges (1-based)."""
    # Flatten into (paragraph, page_no) units
    units: list[tuple[str, int]] = []
    for pno, page in enumerate(pages, start=1):
        for para in page.split("\n\n"):
            para = para.strip()
            if para:
                units.append((para, pno))

    chunks: list[Chunk] = []
    buf: list[tuple[str, int]] = []
    size = 0

    def flush():
        nonlocal buf, size
        if not buf:
            return
        text = "\n\n".join(t for t, _ in buf).strip()
        if len(text) >= MIN_CHUNK_CHARS:
            chunks.append(Chunk(text=text, page_start=buf[0][1], page_end=buf[-1][1]))
        # keep overlap tail
        tail, tail_size = [], 0
        for t, p in reversed(buf):
            tail_size += len(t)
            tail.insert(0, (t, p))
            if tail_size >= OVERLAP_CHARS:
                break
        buf, size = tail, sum(len(t) for t, _ in tail)

    for para, pno in units:
        # very long paragraph: hard-split on sentences
        while len(para) > CHUNK_CHARS:
            cut = para.rfind(". ", 0, CHUNK_CHARS)
            cut = cut + 1 if cut > CHUNK_CHARS // 2 else CHUNK_CHARS
            piece, para = para[:cut].strip(), para[cut:].strip()
            buf.append((piece, pno))
            size += len(piece)
            flush()
        buf.append((para, pno))
        size += len(para)
        if size >= CHUNK_CHARS:
            flush()

    # final flush without overlap-retention
    if buf:
        text = "\n\n".join(t for t, _ in buf).strip()
        if len(text) >= MIN_CHUNK_CHARS:
            chunks.append(Chunk(text=text, page_start=buf[0][1], page_end=buf[-1][1]))

    for i, c in enumerate(chunks):
        c.index = i
    return chunks


def build_rows(gfile_id: str, doc_name: str, drive_id: int, chunks: list[Chunk],
               vectors: list[list[float]], agency: str = "", year: int = 0) -> list[dict]:
    """Assemble Milvus upsert rows from chunks + embeddings."""
    rows = []
    for c, v in zip(chunks, vectors):
        rows.append({
            "pk": f"{gfile_id}_{c.index}",
            "vector": v,
            "text": c.text[:16000],
            "doc_id": gfile_id,
            "doc_name": doc_name[:500],
            "drive_id": drive_id,
            "agency": agency,
            "page_start": c.page_start,
            "page_end": c.page_end,
            "year": year,
        })
    return rows
