# Setup Guide — Put Your App on the Internet (Simple Steps)

After this setup, your app will run on Hugging Face's computers — **not yours**. Your PC can be off. You (and your users) open it from any phone or laptop browser using one link.

Total time: about 45–60 minutes. Everything is free. No credit card anywhere.

You will create 4 free accounts. Use the same email everywhere to keep it simple.

---

## STEP 1 — Supabase (this stores your users and file records)

1. Open **https://supabase.com** and click **"Start your project"** (green button, top right).
2. Sign up with your Google account (easiest).
3. Click **"New project"**.
   - Name: `pharma-rag`
   - Database Password: click **Generate a password**, then **COPY IT AND SAVE IT in your notes app**. You will need it in a minute.
   - Region: pick **Southeast Asia (Singapore)** (closest to India).
   - Click **"Create new project"**. Wait ~2 minutes.
4. Get your connection text:
   - Click the **"Connect"** button at the top of the page.
   - A window opens. Under **"Connection String"**, choose the tab **"URI"**.
   - Under Method/Type, pick **"Session pooler"** if you see that choice.
   - Copy the long text that starts with `postgresql://...`
   - In that text, replace `[YOUR-PASSWORD]` with the database password you saved.
5. **Save this final text in your notes as: `DATABASE_URL`**

---

## STEP 2 — Zilliz Cloud (this stores your 500k pages as searchable data)

1. Open **https://cloud.zilliz.com** and click **"Sign Up"** → use Google sign-in.
2. It will ask you to create a cluster. Choose the **Free** plan (sometimes called "Serverless / Free", 5 GB). Any region is fine (pick Singapore/Asia if offered).
3. Name it `pharma-rag` and create it. Wait ~1 minute.
4. Click on your new cluster. You will see:
   - **Public Endpoint** — a link starting with `https://in0…`. Copy it. **Save as: `ZILLIZ_URI`**
   - **Token / API Key** — click the copy icon next to it (or go to the **API Keys** section on the left menu and create one). **Save as: `ZILLIZ_TOKEN`**

---

## STEP 3 — Free AI model keys (the "brains")

Get at least the first two. Each one you add makes the app faster for more users.

**Groq (most important):**
1. Open **https://console.groq.com** → sign in with Google.
2. Left menu → **API Keys** → **Create API Key** → name it `pharma-rag` → Copy the key (starts with `gsk_`).
3. **Save as: `GROQ_API_KEY`**

**Google Gemini (second most important):**
1. Open **https://aistudio.google.com** → sign in with Google.
2. Click **"Get API key"** (top left) → **"Create API key"** → Copy it.
3. **Save as: `GEMINI_API_KEY`**

**Tavily (for web-search answers):**
1. Open **https://www.tavily.com** → **Sign up** → after login, your API key is shown on the dashboard. Copy it.
2. **Save as: `TAVILY_API_KEY`**

**Optional extras (do later, anytime):** OpenRouter (https://openrouter.ai → sign in → Keys), Mistral (https://console.mistral.ai), NVIDIA (https://build.nvidia.com), Cerebras (https://cloud.cerebras.ai). Add them the same way as Space secrets named `OPENROUTER_API_KEY`, `MISTRAL_API_KEY`, `NVIDIA_API_KEY`, `CEREBRAS_API_KEY`.

---

## STEP 4 — Google Drive access (ALREADY HALF DONE ✅)

You already have the key file: **`csv-guidelines-427f498ae325.json`** (it is in your "RAG For Pharma Guidelines" folder).

1. Open that file with TextEdit/Notepad. Select ALL the text and copy it. **Save as: `GOOGLE_SERVICE_ACCOUNT_JSON`**
2. Now give this robot account permission to read your guideline folders:
   - Open Google Drive → right-click your guidelines folder → **Share**.
   - Add this email: **`csv-guideline@csv-guidelines.iam.gserviceaccount.com`**
   - Role: **Viewer** → Send.
   - Repeat for every guidelines folder/drive you have.

---

## STEP 5 — Put the app online with GitHub + Render (both free, no card)

*(Note: Hugging Face now marks Docker/Gradio hosting as "Paid" on some accounts, so we use Render.com instead. Render's free plan needs no credit card.)*

**5A. Put the code on GitHub** (Render reads the code from there)

1. Open **https://github.com/join** and create a free account (verify your email).
2. Open **https://github.com/new**:
   - Repository name: `pharma-rag`
   - Choose **Private**
   - Click **"Create repository"**.
3. On the next page, click the link **"uploading an existing file"** (it's in the small text: "…or uploading an existing file").
4. On your computer open the folder `RAG For Pharma Guidelines/pharma-rag-web` and drag EVERYTHING inside it into the upload box: the `backend`, `frontend`, `ingest`, `supabase` folders and the files `README.md`, `requirements.txt`, `requirements-render.txt`, `render.yaml`, `app.py`, `Dockerfile`, `.env.example`, `run_local.sh`.
   (Don't worry about files starting with a dot — they're optional.)
5. Click the green **"Commit changes"** button at the bottom. Wait for the upload to finish.

**5B. Deploy on Render**

1. Open **https://render.com** → click **"Get Started"** → choose **"Sign up with GitHub"** (one click, connects everything).
2. On the Render dashboard, click **"+ New"** (top right) → **"Web Service"**.
3. It shows your GitHub repositories → click **"Connect"** next to **pharma-rag**.
   (If you don't see it: click "Configure account" → give Render access to the repo.)
4. Fill the form:
   - Name: `pharma-rag`
   - Language: **Python 3**
   - Branch: `main`
   - Build Command — replace whatever is there with:
     `pip install -r requirements-render.txt && python -c "from backend.app.rag.embeddings import warmup; warmup()"`
   - Start Command — replace with:
     `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
   - Instance Type: **Free**
5. Scroll down to **"Environment Variables"** → click **"Add Environment Variable"** for each of these (Name exactly as written, Value from your notes):

   | Name | Value |
   |---|---|
   | `PYTHON_VERSION` | `3.11.9` |
   | `EMBEDDING_BACKEND` | `onnx` |
   | `SECRET_KEY` | `BaDbuvoLtbDO3WEbxkpiZvFA-QdnLnUHPXgGKSFVLBGun0SGDLos8Gg1dgWmjnJ-` (or any long random text) |
   | `DATABASE_URL` | from Step 1 |
   | `ZILLIZ_URI` | from Step 2 |
   | `ZILLIZ_TOKEN` | from Step 2 |
   | `GROQ_API_KEY` | from Step 3 |
   | `GEMINI_API_KEY` | from Step 3 |
   | `TAVILY_API_KEY` | from Step 3 |
   | `GOOGLE_SERVICE_ACCOUNT_JSON` | from Step 4 (paste the whole JSON text) |
   | `INVITE_CODE` | any word you choose, e.g. `pharma2026` — people need this word to register. Skip if anyone may register. |

6. Click **"Deploy Web Service"** at the bottom. A black log window opens — wait ~5–10 minutes until it says **"Your service is live"**.

**Your app link is shown at the top of the page: `https://pharma-rag-XXXX.onrender.com`**

Open this link on your phone — it works anywhere, PC off.

*Updating the app later: just upload changed files to GitHub the same way (or "Add file" → "Upload files" in the repo) — Render redeploys automatically.*

---

## STEP 6 — First login (claim your admin seat)

1. Open your app link → click **Register** → enter YOUR email + a password.
   ⚠️ **The very first account becomes the Admin. Register yourself first!**
2. Click the **Admin** button (bottom-left) → **Models** tab → click **"↻ Refresh free models"**. All free models from your keys appear. Tick/untick what users may pick.
3. **Drives** tab → add your guideline folder:
   - In Google Drive, open the folder. Look at the browser address bar: `https://drive.google.com/drive/folders/XXXXXXXXXXXX` — the `XXXXXXXXXXXX` part is the **Folder ID**.
   - Paste it in, give it a name (e.g. "FDA Guidelines"), click **Add drive**.
4. Share the app link + invite code with your users. They register and can only search — they never see the Admin panel.

---

## STEP 7 — Load your 500k pages (one-time, on your Mac)

The big first-time loading runs on YOUR Mac (the free server is too small for it). Open Terminal:

```bash
cd "/Users/souvikdatta/Downloads/Python Learning/My Programs/RAG For Pharma Guidelines/pharma-rag-web"
python3 -m venv .venv && source .venv/bin/activate
pip install -r ingest/requirements.txt
cp .env.example .env
open -e .env    # fill in DATABASE_URL, ZILLIZ_URI, ZILLIZ_TOKEN, GOOGLE_SERVICE_ACCOUNT_JSON — same values as Step 5
```

Then:
```bash
python -m ingest.ingest --sync-manifest    # finds all files in your Drive (fast)
python -m ingest.ingest --list             # shows how many files are waiting
python -m ingest.ingest --run --limit 500  # processes 500 files; run again tomorrow for more
```
You can stop anytime (Ctrl-C) — it remembers what's done and continues next time. Spread it over several evenings. Your Mac only needs to be ON during this loading — after that, never again.

New guidelines later? Just drop them in Drive and press **Sync** in the Admin panel — no Mac needed.

---

## STEP 8 — Keep it awake (5 minutes, important)

Render's free plan puts the app to sleep after 15 quiet minutes (waking takes ~1 minute). A free pinger keeps it awake and also stops Supabase from pausing:

1. Open **https://cron-job.org** → **Sign up** free.
2. Click **"Create cronjob"**:
   - Title: `pharma-rag keepalive`
   - URL: `https://pharma-rag-XXXX.onrender.com/api/health/db` (your Render link + `/api/health/db`)
   - Schedule: **every 10 minutes**
   - Click **Create**.

Note: Render gives 750 free hours per month — one service running 24/7 uses ~744, so keeping it always-awake is fine as long as this is your only free Render service.

---

## Quick problem-solving

- **Build fails on Render** → open the "Logs" tab on your service, copy the red text, and show it to me.
- **"Deploy failed" / crash after build** → usually a wrongly pasted variable. Check `DATABASE_URL` (password replaced?) and `GOOGLE_SERVICE_ACCOUNT_JSON` (whole JSON pasted?). Edit them under the service's **Environment** tab, then click "Manual Deploy" → "Deploy latest commit".
- **App loads but answers say "no provider configured"** → your `GROQ_API_KEY` / `GEMINI_API_KEY` variables are missing or misspelled.
- **Search finds nothing** → ingestion hasn't run yet (Step 7), or the Drive folder wasn't shared with the robot email (Step 4).
- **First visit is slow (~1 min)** → the app was asleep; the cron-job in Step 8 prevents this.
- **"Out of memory" in Render logs** → add environment variable `EMBEDDING_ONNX_FILE` = `onnx/model_quantized.onnx` (a smaller version of the search model) and redeploy.
