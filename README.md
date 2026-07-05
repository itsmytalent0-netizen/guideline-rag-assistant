# Guideline RAG Assistant

This project is a free-first RAG system for Pharm/Biotech Computer System
Validation guideline files.

It supports:

- Google Drive document ingestion
- manual file upload for quick testing
- PDF, DOCX, image OCR, TXT, CSV, XLS, and XLSX support
- text-based retrieval using BM25 keyword search
- meaning-based retrieval using embeddings and Chroma vector DB
- hybrid retrieval combining both methods
- provider-independent LLM answers through any OpenAI-compatible API
- retrieval-only mode when no LLM key is configured

## Quick Local Run

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## LLM-Agnostic Design

The app does not depend on Codex. Codex can help build and modify it, but the
running RAG app talks to an LLM through environment variables:

```text
LLM_BASE_URL
LLM_API_KEY
LLM_MODEL
```

If the provider supports OpenAI-compatible chat completions, it can be connected.
That usually includes OpenRouter, LiteLLM, many gateway services, and some custom
model routers.

If no LLM is configured, the app still works in retrieval-only mode.

## Supported Files

The app can index these file types:

- PDF
- Word DOCX
- PNG/JPG/JPEG images through OCR
- TXT
- CSV
- XLS/XLSX spreadsheets

Scanned PDFs may need OCR before upload unless their text is selectable.

## Google Drive Access

For hosted use, create a Google Cloud service account and share your Drive folder
with the service account email. Add these hosting secrets:

```text
GOOGLE_DRIVE_FOLDER_ID
GOOGLE_SERVICE_ACCOUNT_JSON
```

The folder ID is the long string in your Google Drive folder URL. The Drive
folder can contain validation PDFs, Word files, images, text files, and
spreadsheet files.

## Recommended Hosted Setup

Use Hugging Face Spaces or Streamlit Community Cloud for the app. The app can be
opened from mobile, laptop, or tablet through the hosted URL.

For a more permanent production database later, the `src` modules are separated
so Chroma can be replaced with Supabase `pgvector` or Qdrant Cloud without
changing the user interface.
