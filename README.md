# Guideline RAG Assistant

This project is a free-first RAG system for Pharm/Biotech guideline CSV files.

It supports:

- Google Drive CSV ingestion
- manual CSV upload for quick testing
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

## Google Drive Access

For hosted use, create a Google Cloud service account and share your Drive folder
with the service account email. Add these hosting secrets:

```text
GOOGLE_DRIVE_FOLDER_ID
GOOGLE_SERVICE_ACCOUNT_JSON
```

The folder ID is the long string in your Google Drive folder URL.

## Recommended Hosted Setup

Use Hugging Face Spaces or Streamlit Community Cloud for the app. The app can be
opened from mobile, laptop, or tablet through the hosted URL.

For a more permanent production database later, the `src` modules are separated
so Chroma can be replaced with Supabase `pgvector` or Qdrant Cloud without
changing the user interface.
