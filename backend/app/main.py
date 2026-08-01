# ── FastAPI Application Factory ───────────────────────────────────────────────
# Creates and configures the ASGI app with CORS, routers, and lifespan events.

from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base, AsyncSessionLocal
from app.routers.auth import router as auth_router
from app.routers.knowledge import router as knowledge_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown logic.

    Startup: create upload directory + build in-memory FAISS index from pgvector.
    Shutdown: dispose of the DB engine's connection pool.
    """
    # Ensure the upload directory exists for knowledge-base files
    Path(settings.UPLOAD_DIR).resolve().mkdir(parents=True, exist_ok=True)

    # Build the FAISS index from all existing DocumentChunk rows in pgvector.
    # This must happen after migrations (Alembic runs before uvicorn in CMD).
    from app.services.faiss_service import get_faiss_service

    async with AsyncSessionLocal() as db:
        try:
            await get_faiss_service().build_index(db)
        except Exception:
            # If the document_chunks table doesn't exist yet (first run before
            # migrations), log and continue — the index will be populated on
            # first ingestion.
            import logging
            logging.getLogger(__name__).warning(
                "FAISS index build skipped — table may not exist yet."
            )

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
