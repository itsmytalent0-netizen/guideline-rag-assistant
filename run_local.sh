#!/usr/bin/env bash
# Local development: runs the app on http://localhost:7860 with sqlite fallback
# (set DATABASE_URL in .env to use Supabase instead).
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install -r requirements.txt
fi
./.venv/bin/uvicorn backend.app.main:app --reload --port 7860
