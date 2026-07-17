# Render.com deployment (Docker). Free tier: 512 MB RAM.
# Lightweight: query embedding runs on onnxruntime (same bge-small model,
# same vectors as the Mac ingestion) — no torch, fits the free instance.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    EMBEDDING_BACKEND=onnx \
    HF_HOME=/app/.hf-cache

WORKDIR /app

# Install Python deps (fastapi, onnxruntime, pymilvus, etc.)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY backend ./backend
COPY frontend ./frontend

# Pre-download the small ONNX embedding model so the first question is fast.
# Non-fatal: if the download is unavailable at build time, it happens on first use.
RUN python -c "from backend.app.rag.embeddings import warmup; warmup()" || echo "warmup skipped; model will load on first request"

# Render provides $PORT; fall back to 10000 locally.
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
