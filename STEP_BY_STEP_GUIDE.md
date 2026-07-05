# Step-by-Step Setup Guide

This guide explains what to click, where to find each option, and why each step is
needed.

## What We Built

You now have a web app called **Guideline RAG Assistant**.

It can:

- read guideline CSV files
- search by exact words
- search by meaning
- combine both search styles
- optionally ask any OpenAI-compatible LLM to write a source-grounded answer

Codex is only the builder. The app itself can connect to another LLM provider.

## Step 1: Put CSV Files In One Google Drive Folder

1. Open [Google Drive](https://drive.google.com).
2. Click **New**.
3. Click **Folder**.
4. Name it something like `Guideline RAG CSV`.
5. Upload your Pharm/Biotech CSV files into this folder.

Why this is needed:

The app needs one fixed folder to read from. This prevents it from scanning your
entire Google Drive.

## Step 2: Copy The Google Drive Folder ID

1. Open the folder in Google Drive.
2. Look at the browser address bar.
3. The URL will look like this:

```text
https://drive.google.com/drive/folders/1ABCxyzYourFolderIdHere
```

4. Copy only the long part after `/folders/`.

Why this is needed:

The app uses this folder ID to know where your CSV files are.

## Step 3: Create A Google Cloud Service Account

1. Open [Google Cloud Console](https://console.cloud.google.com).
2. Click the project selector at the top.
3. Click **New Project**.
4. Give it a name, for example `Guideline RAG`.
5. Click **Create**.
6. In the top search bar, search for **Google Drive API**.
7. Open **Google Drive API**.
8. Click **Enable**.

Why this is needed:

The hosted app needs permission to read your Google Drive folder. The Drive API is
the official way to do that.

## Step 4: Create The Service Account Key

1. In Google Cloud Console, open the left menu.
2. Go to **IAM & Admin**.
3. Click **Service Accounts**.
4. Click **Create service account**.
5. Name it `guideline-rag-reader`.
6. Click **Create and Continue**.
7. You can skip role selection for now.
8. Click **Done**.
9. Open the service account you just created.
10. Click the **Keys** tab.
11. Click **Add key**.
12. Click **Create new key**.
13. Choose **JSON**.
14. Click **Create**.

This downloads a JSON file.

Why this is needed:

This JSON file is the app's login credential for Google Drive. We do not put it
directly in the code. We paste it into the hosting provider's secret settings.

## Step 5: Share Your Drive Folder With The Service Account

1. Open the downloaded JSON file.
2. Find the value called `client_email`.
3. Copy that email address.
4. Go back to your Google Drive CSV folder.
5. Right-click the folder.
6. Click **Share**.
7. Paste the service account email.
8. Give it **Viewer** access.
9. Click **Send** or **Share**.

Why this is needed:

The service account is like a separate Google user. It cannot see your files until
you explicitly share the folder with it.

## Step 6: Choose Where To Host The App

Recommended simple options:

- Hugging Face Spaces
- Streamlit Community Cloud

Either option gives you a web URL that works from mobile, tablet, or another
laptop. Your laptop does not need to stay on.

Why this is needed:

If the app runs only on your laptop, your mobile cannot use it when the laptop is
off. Hosting keeps the app available online.

## Step 7A: Deploy On Streamlit Community Cloud

1. Put this project on GitHub.
2. Open [Streamlit Community Cloud](https://share.streamlit.io).
3. Sign in.
4. Click **Create app**.
5. Choose your GitHub repository.
6. Set the main file path to:

```text
app.py
```

7. Click **Deploy**.

Why this is needed:

Streamlit Cloud reads `requirements.txt`, installs the app, and gives you a
shareable web link.

## Step 7B: Add Streamlit Secrets

1. Open your deployed app in Streamlit Cloud.
2. Click **Manage app**.
3. Click **Settings**.
4. Click **Secrets**.
5. Add values like this:

```toml
GOOGLE_DRIVE_FOLDER_ID = "paste-your-folder-id"
GOOGLE_SERVICE_ACCOUNT_JSON = """paste-your-full-json-file-here"""

LLM_PROVIDER = "openai_compatible"
LLM_BASE_URL = "https://openrouter.ai/api/v1"
LLM_API_KEY = "paste-your-provider-key"
LLM_MODEL = "paste-model-name"
```

6. Click **Save**.
7. Restart the app if Streamlit asks.

Why this is needed:

Secrets keep private values out of your code. The app reads them at runtime.

## Step 8: Connect Any LLM Provider

Use any provider that gives an OpenAI-compatible API.

You need three things:

```text
LLM_BASE_URL
LLM_API_KEY
LLM_MODEL
```

Examples:

```toml
LLM_BASE_URL = "https://openrouter.ai/api/v1"
LLM_MODEL = "openai/gpt-4o-mini"
```

For a LiteLLM proxy:

```toml
LLM_BASE_URL = "https://your-litellm-server.example.com"
LLM_MODEL = "your-model-name"
```

For Ollama, it works only when Ollama is reachable by the hosted app:

```toml
LLM_BASE_URL = "http://your-ollama-server:11434/v1"
LLM_API_KEY = "ollama"
LLM_MODEL = "llama3.1"
```

Why this is needed:

This makes the app independent of Codex. You can switch model providers by
changing settings instead of rewriting the RAG system.

## Step 9: Use The App

1. Open the app URL on mobile or laptop.
2. In the left panel, click **Index Google Drive folder**.
3. Wait for the success message.
4. Type a question in **Ask a guideline question**.
5. Choose retrieval mode:
   - **Hybrid**: best default
   - **Text only**: exact terms, product names, abbreviations
   - **Meaning only**: conceptual questions
6. Turn **Generate answer** on if you configured an LLM.
7. Click **Search**.

Why this is needed:

Indexing converts CSV rows into searchable guideline chunks. Searching retrieves
the most relevant chunks. The LLM, if enabled, writes a readable answer using
those chunks.

## Step 10: Add Or Update CSV Files

1. Add new CSV files to the same Google Drive folder.
2. Open the app.
3. Click **Index Google Drive folder** again.

Why this is needed:

The app does not automatically read every Drive change yet. Re-indexing refreshes
the search database.

## First Test Without Google Drive

Before setting up Google Drive, you can test the app manually:

1. Open the app.
2. In the left panel, click **Upload CSV files**.
3. Select one or more CSV files.
4. Click **Index uploaded CSVs**.
5. Ask a question.

Why this is useful:

It confirms the retrieval system works before you spend time on Google setup.
