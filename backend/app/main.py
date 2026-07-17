"""FastAPI entry point. Serves the API, the static frontend, and the MCP endpoint."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import engine
from .models import Base
from .routes_admin import router as admin_router
from .routes_auth import router as auth_router
from .routes_chat import router as chat_router
from .routes_meta import router as meta_router
from .routes_pages import router as pages_router

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")

# MCP app must be created before FastAPI so its lifespan can be composed
_mcp_app = None
try:
    from .mcp_server import build_mcp_app
    _mcp_app = build_mcp_app()
except Exception:  # noqa: BLE001
    logging.getLogger(__name__).exception("MCP init failed; continuing without it")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    if _mcp_app is not None:
        async with _mcp_app.lifespan(_mcp_app):
            yield
    else:
        yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(meta_router)
app.include_router(pages_router)

if _mcp_app is not None:
    app.mount("/mcp", _mcp_app)

if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
