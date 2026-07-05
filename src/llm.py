from __future__ import annotations

from openai import OpenAI

from src.config import AppConfig
from src.models import SearchResult


SYSTEM_PROMPT = """You answer questions using only the supplied guideline context.
If the context is insufficient, say that the indexed guidelines do not contain enough information.
Keep the answer concise and include source filenames and row numbers when relevant."""


def build_context(results: list[SearchResult]) -> str:
    blocks = []
    for index, result in enumerate(results, start=1):
        metadata = result.document.metadata
        source = metadata.get("source_name", "CSV")
        row = metadata.get("row_number", "?")
        blocks.append(
            f"[Source {index}: {source}, row {row}]\n{result.document.text}"
        )
    return "\n\n".join(blocks)


def generate_answer(config: AppConfig, question: str, results: list[SearchResult]) -> str:
    client_kwargs = {"api_key": config.llm_api_key}
    if config.llm_base_url:
        client_kwargs["base_url"] = config.llm_base_url
    client = OpenAI(**client_kwargs)

    context = build_context(results)
    response = client.chat.completions.create(
        model=config.llm_model,
        temperature=0.1,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Question:\n{question}\n\nGuideline context:\n{context}",
            },
        ],
    )
    return response.choices[0].message.content or ""
