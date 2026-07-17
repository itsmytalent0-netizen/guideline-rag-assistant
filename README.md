---
title: Pharma Guidelines RAG
emoji: 💊
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 5.34.0
app_file: app.py
pinned: false
---

<!-- NOTE: If the Docker SDK is available (free) on your account, you can use it
instead: change the frontmatter above to `sdk: docker` + `app_port: 7860` and
the included Dockerfile will be used. The Gradio SDK setup below works on the
free tier everywhere. -->


# Pharma Guidelines RAG — free, multi-user, internet-hosted

Chat over ~500k pages of pharmaceutical guidelines (Google Drive master data) **or** the live web. Admins manage master data, ingestion, models, and users; everyone else searches. Runs entirely on free tiers — no credit card anywhere.

| Piece | Service (free tier) |
|---|---|
| App hosting | Hugging Face Spaces (Docker, 2 vCPU / 16 GB) |
| Vectors + chunk text | Zilliz Cloud serverless (5 GB) |
| Users / metadata / history | Supabase Postgres (500 MB) |
| LLMs | Groq, Gemini, OpenRouter (:free), Mistral, NVIDIA NIM, GitHub Models, Cerebras — auto-rotated |
| Web search | Tavily (1,000/mo) + DuckDuckGo fallback |
| Bulk ingestion | Your own computer (checkpointed CLI, multi-day friendly) |

---

## Setup — step by step (~1 hour)

### 1. Supabase (metadata DB)
1. Create a free project at supabase.com (no card).
2. Project Settings → Database → copy the **connection string (URI)** — this is `DATABASE_URL`.
3. (Optional) Run `supabase/schema.sql` in the SQL editor; otherwise the app auto-creates tables on first boot.

### 2. Zilliz Cloud (vector DB)
1. Create a free serverless cluster at cloud.zilliz.com (no card, 5 GB).
2. Copy the cluster **public endpoint** → `ZILLIZ_URI`, and an **API key** → `ZILLIZ_TOKEN`.

### 3. Free LLM API keys (add as many as you can — each adds capacity)
- Groq: console.groq.com → API key
- Google Gemini: aistudio.google.com → Get API key
- OpenRouter: openrouter.ai → API key (free `:free` models)
- Mistral: console.mistral.ai → free tier key
- NVIDIA: build.nvidia.com → API key
- GitHub Models: a GitHub personal access token (`models:read` scope)
- Cerebras: cloud.cerebras.ai → API key
- Tavily (web search): tavily.com → free key

### 4. Google Drive service account
1. In Google Cloud Console: create a project → enable **Google Drive API** → create a **Service Account** → download its JSON key.
2. Share every guideline folder in Drive with the service account's email (Viewer).
3. The whole JSON (or its base64) becomes `GOOGLE_SERVICE_ACCOUNT_JSON`.

### 5. Deploy to Hugging Face Spaces
1. Create a free account at huggingface.co, then **New Space** → SDK: **Docker** → visibility Public or Private.
2. Push this folder to the Space repo:
   ```bash
   cd pharma-rag-web
   git init && git add . && git commit -m "initial"
   git remote add space https://huggingface.co/spaces/YOURNAME/pharma-rag
   git push space main
   ```
3. Space **Settings → Variables and secrets**: add every value from `.env.example` (SECRET_KEY, DATABASE_URL, ZILLIZ_URI, ZILLIZ_TOKEN, the LLM keys, TAVILY_API_KEY, GOOGLE_SERVICE_ACCOUNT_JSON, and optionally INVITE_CODE).
4. First build takes ~10 min. Your app is then live at `https://YOURNAME-pharma-rag.hf.space`.

### 6. First run
1. Open the app and **register — the first account automatically becomes admin.**
2. Admin → **Models → Refresh** to pull the live free-model catalog from every provider; toggle which ones users may pick.
3. Admin → **Drives** → add each Drive folder ID (the part after `/folders/` in its URL).
4. Set `INVITE_CODE` if you want to gate registration.

### 7. Bulk ingestion (on your Mac — NOT the server)
```bash
cd pharma-rag-web
python3 -m venv .venv && source .venv/bin/activate
pip install -r ingest/requirements.txt
cp .env.example .env   # fill in DATABASE_URL, ZILLIZ_*, GOOGLE_SERVICE_ACCOUNT_JSON

python -m ingest.ingest --sync-manifest   # register all Drive files (fast)
python -m ingest.ingest --list            # see counts
python -m ingest.ingest --run --limit 500 # process a batch; repeat any day
python -m ingest.ingest --run             # or let it run to completion
```
Fully resumable — Ctrl-C anytime; progress is stored per file in Supabase. Spread the 500k pages over as many evenings as you like. Scanned PDFs are flagged `needs_ocr`; install `ocrmypdf` (`brew install ocrmypdf`) and re-run with `--ocr`.

Later additions to Drive **don't** need the CLI: the admin panel's **Sync** button picks up new/changed/deleted files on the server.

### 8. Keep-alive (prevents free-tier sleeping)
Push the repo to GitHub too, add repo secret `APP_URL` = your Space URL; `.github/workflows/keepalive.yml` pings the app + DB every 12 h.

---

## MCP endpoint (optional)
The server also speaks MCP at `https://<your-space>/mcp` (streamable HTTP) with tools `search_guidelines`, `ask_guidelines`, `list_documents`. Authenticate with the `X-API-Key` header — every user has a key under the **API key** button in the sidebar.

## Local development
```bash
./run_local.sh        # http://localhost:7860 (sqlite fallback, no external services needed for UI/auth)
```

## Architecture, phases, free-tier math
See `../IMPLEMENTATION_PLAN.md`.
