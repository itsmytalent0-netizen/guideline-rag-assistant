"""Hugging Face Spaces entry point (Gradio SDK — free tier).

HF's free tier sometimes marks the Docker SDK as paid; the Gradio SDK runs
Python just the same. This file serves our full FastAPI app (chat UI, API,
MCP) on the Space port, with a tiny Gradio status page mounted at /gradio to
keep the SDK happy.

The real app is at "/" exactly as with the Docker deployment.
"""
import gradio as gr
import uvicorn

from backend.app.main import app  # the full FastAPI application

with gr.Blocks(title="Pharma RAG — status") as demo:
    gr.Markdown(
        "## 💊 Pharma Guidelines RAG\n"
        "The application UI is served at the root URL — "
        "[open the app](/) \n\n"
        "(This page only exists to satisfy the Gradio SDK.)"
    )

app = gr.mount_gradio_app(app, demo, path="/gradio")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
