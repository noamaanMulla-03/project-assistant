# ── FastAPI Application Factory ───────────────────────────────────────────────
# Creates and configures the ASGI app with CORS, routers, and lifespan events.

from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base
from app.routers.auth import router as auth_router
from app.routers.knowledge import router as knowledge_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown logic.

    On startup we ensure the upload directory exists.
    """
    # Ensure the upload directory exists for knowledge-base files
    Path(settings.UPLOAD_DIR).resolve().mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown: dispose of the engine's connection pool
    await engine.dispose()


# ── App Instance ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Project Assistant API",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS Middleware ───────────────────────────────────────────────────────────
# Allow the Vite dev server (and the docker-compose service name) to make
# credentialed requests (cookies).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(knowledge_router)


# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health_check():
    """Simple liveness probe for Docker / orchestrators."""
    return {"status": "ok"}
