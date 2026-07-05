from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from src.config import AppConfig
from src.drive_loader import load_files_from_drive
from src.ingestion import SUPPORTED_EXTENSIONS, file_to_documents
from src.llm import generate_answer
from src.retriever import HybridRetriever


st.set_page_config(
    page_title="Guideline RAG Assistant",
    page_icon="G",
    layout="wide",
)


@st.cache_resource(show_spinner=False)
def get_retriever(config: AppConfig) -> HybridRetriever:
    return HybridRetriever(config=config)


def read_uploaded_files(files) -> list[tuple[str, bytes, str]]:
    uploaded = []
    for file in files:
        uploaded.append((file.name, file.getvalue(), file.type or ""))
    return uploaded


def index_files(retriever: HybridRetriever, files: list[tuple[str, bytes, str]]) -> int:
    docs = []
    for filename, data, mime_type in files:
        docs.extend(file_to_documents(filename, data, mime_type))
    retriever.index_documents(docs)
    return len(docs)


def sidebar(config: AppConfig, retriever: HybridRetriever) -> None:
    st.sidebar.header("Data")

    uploaded_files = st.sidebar.file_uploader(
        "Upload CSV validation files",
        type=sorted(extension.strip(".") for extension in SUPPORTED_EXTENSIONS),
        accept_multiple_files=True,
    )

    if st.sidebar.button("Index uploaded files", use_container_width=True):
        if not uploaded_files:
            st.sidebar.warning("Choose one or more validation files first.")
        else:
            with st.spinner("Reading and indexing validation files..."):
                count = index_files(retriever, read_uploaded_files(uploaded_files))
            st.sidebar.success(f"Indexed {count} guideline chunks.")

    st.sidebar.divider()

    if st.sidebar.button("Index Google Drive folder", use_container_width=True):
        if not config.google_drive_folder_id:
            st.sidebar.error("Add GOOGLE_DRIVE_FOLDER_ID first.")
        elif not config.google_service_account_json:
            st.sidebar.error("Add GOOGLE_SERVICE_ACCOUNT_JSON first.")
        else:
            with st.spinner("Reading validation files from Google Drive..."):
                files = load_files_from_drive(config)
                count = index_files(retriever, files)
            st.sidebar.success(f"Indexed {count} guideline chunks from Drive.")

    st.sidebar.divider()
    st.sidebar.caption(f"Indexed chunks: {retriever.count()}")


def main() -> None:
    config = AppConfig.from_environment()
    retriever = get_retriever(config)
    sidebar(config, retriever)

    st.title("Guideline RAG Assistant")

    col_a, col_b, col_c = st.columns([1, 1, 1])
    with col_a:
        mode = st.radio(
            "Retrieval mode",
            ["Hybrid", "Text only", "Meaning only"],
            index=0,
            horizontal=True,
        )
    with col_b:
        top_k = st.slider("Sources", min_value=3, max_value=12, value=6)
    with col_c:
        use_llm = st.toggle("Generate answer", value=config.llm_is_configured)

    question = st.text_area(
        "Ask a guideline question",
        placeholder="Example: What evidence is required for computer system validation?",
        height=110,
    )

    if st.button("Search", type="primary", use_container_width=True):
        if not question.strip():
            st.warning("Type a question first.")
            return
        if retriever.count() == 0:
            st.warning("Index validation files first using the left panel.")
            return

        with st.spinner("Finding the most relevant guideline text..."):
            results = retriever.search(question, mode=mode, top_k=top_k)

        if use_llm and config.llm_is_configured:
            with st.spinner("Generating a source-grounded answer..."):
                answer = generate_answer(config, question, results)
            st.subheader("Answer")
            st.write(answer)
        elif use_llm and not config.llm_is_configured:
            st.info("No LLM is configured yet. Showing retrieval results only.")

        st.subheader("Sources")
        for idx, result in enumerate(results, start=1):
            meta = result.document.metadata
            location = meta.get("page_number") or meta.get("row_number") or meta.get("chunk_number", "?")
            with st.expander(
                f"{idx}. {meta.get('source_name', 'Document')} location {location} "
                f"- score {result.score:.3f}",
                expanded=idx <= 3,
            ):
                st.write(result.document.text)
                st.json(meta)


if __name__ == "__main__":
    Path(os.getenv("VECTOR_DB_DIR", ".rag/chroma")).mkdir(parents=True, exist_ok=True)
    main()
