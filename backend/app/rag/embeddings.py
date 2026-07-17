"""Embedding service — bge-small-en-v1.5 (384-dim), two interchangeable backends:

- "torch":  sentence-transformers (used on your Mac for bulk ingestion; MPS GPU)
- "onnx":   onnxruntime + tokenizers (~4x lighter RAM — used on small free
            servers like Render's 512 MB instances). Same model weights, same
            vectors (fp32 export), so ingestion and queries stay compatible.

Backend selection: EMBEDDING_BACKEND env (torch|onnx|auto). "auto" uses torch
if sentence-transformers is installed, else onnx.
"""
import threading

from ..config import get_settings

settings = get_settings()

_backend = None
_lock = threading.Lock()

ONNX_REPO = "Xenova/bge-small-en-v1.5"


class _TorchBackend:
    def __init__(self):
        import torch
        from sentence_transformers import SentenceTransformer
        device = ("mps" if torch.backends.mps.is_available()
                  else "cuda" if torch.cuda.is_available() else "cpu")
        self.model = SentenceTransformer(settings.embedding_model, device=device)

    def encode(self, texts: list[str], batch_size: int = 128) -> list[list[float]]:
        vecs = self.model.encode(texts, batch_size=batch_size,
                                 normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vecs]


class _OnnxBackend:
    def __init__(self):
        import numpy as np  # noqa: F401 — fail fast if missing
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        model_path = hf_hub_download(ONNX_REPO, settings.embedding_onnx_file)
        tok_path = hf_hub_download(ONNX_REPO, "tokenizer.json")

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1  # be gentle on tiny free-tier CPUs
        self.session = ort.InferenceSession(model_path, sess_options=opts,
                                            providers=["CPUExecutionProvider"])
        self.input_names = {i.name for i in self.session.get_inputs()}
        self.tokenizer = Tokenizer.from_file(tok_path)
        self.tokenizer.enable_truncation(max_length=512)
        self.tokenizer.enable_padding()

    def encode(self, texts: list[str], batch_size: int = 16) -> list[list[float]]:
        import numpy as np
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            enc = self.tokenizer.encode_batch(batch)
            feed = {"input_ids": np.array([e.ids for e in enc], dtype=np.int64),
                    "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64)}
            if "token_type_ids" in self.input_names:
                feed["token_type_ids"] = np.array([e.type_ids for e in enc], dtype=np.int64)
            hidden = self.session.run(None, feed)[0]
            cls = hidden[:, 0]  # bge models use CLS pooling
            norms = np.linalg.norm(cls, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            out.extend((cls / norms).tolist())
        return out


def _make_backend():
    choice = settings.embedding_backend.lower()
    if choice == "torch":
        return _TorchBackend()
    if choice == "onnx":
        return _OnnxBackend()
    # auto
    try:
        import sentence_transformers  # noqa: F401
        return _TorchBackend()
    except ImportError:
        return _OnnxBackend()


def get_backend():
    global _backend
    if _backend is None:
        with _lock:
            if _backend is None:
                _backend = _make_backend()
    return _backend


# kept for backward compatibility with the ingest CLI
def get_model():
    return get_backend()


def warmup():
    """Download model files + load the session (used at build/deploy time)."""
    get_backend().encode(["warmup"])
    print("Embedding backend ready.")


def embed_passages(texts: list[str], batch_size: int = 128) -> list[list[float]]:
    return get_backend().encode(texts, batch_size=batch_size)


def embed_query(text: str) -> list[float]:
    return get_backend().encode([settings.query_instruction + text])[0]
