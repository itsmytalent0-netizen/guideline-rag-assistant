from __future__ import annotations

import hashlib
import re
from typing import Any

import pandas as pd

from src.models import Document


MAX_CELL_LENGTH = 1200


def normalize_column_name(name: Any) -> str:
    text = str(name).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "column"


def clean_cell(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).replace("\x00", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:MAX_CELL_LENGTH]


def dataframe_to_documents(df: pd.DataFrame, source_name: str) -> list[Document]:
    if df.empty:
        return []

    normalized = df.copy()
    normalized.columns = [normalize_column_name(col) for col in normalized.columns]

    docs: list[Document] = []
    for row_index, row in normalized.iterrows():
        parts = []
        metadata: dict[str, Any] = {
            "source_name": source_name,
            "row_number": int(row_index) + 2,
        }

        for column, value in row.items():
            cleaned = clean_cell(value)
            if not cleaned:
                continue
            parts.append(f"{column}: {cleaned}")
            if column in {"category", "section", "title", "therapy_area", "company", "product"}:
                metadata[column] = cleaned

        text = "\n".join(parts).strip()
        if not text:
            continue

        digest = hashlib.sha256(f"{source_name}:{row_index}:{text}".encode("utf-8")).hexdigest()
        docs.append(Document(id=digest, text=text, metadata=metadata))

    return docs
