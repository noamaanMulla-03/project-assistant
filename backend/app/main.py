# ── FastAPI Application Factory ───────────────────────────────────────────────
# Creates and configures the ASGI app with CORS, routers, and lifespan events.

# Fix passlib 1.7.4 compatibility with bcrypt >=4.0.0
import bcrypt

if not hasattr(bcrypt, "__about__"):
    setattr(
        bcrypt,
        "__about__",
        type("About", (), {"__version__": getattr(bcrypt, "__version__", "4.0.0")}),
    )

from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base, AsyncSessionLocal
from app.routers.auth import router as auth_router
from app.routers.knowledge import router as knowledge_router
from app.routers.project import router as project_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown logic.

    Startup: create upload directory and recover interrupted ingestions.
    Shutdown: dispose of the DB engine's connection pool.
    """
    # Ensure the upload directory exists for knowledge-base files
    Path(settings.UPLOAD_DIR).resolve().mkdir(parents=True, exist_ok=True)

    async with AsyncSessionLocal() as db:
        # ── Recover orphaned documents ──
        # If the container restarted while ingestion was in progress, those
        # documents will be stuck with status='processing' because the
        # background task that was responsible for them no longer exists.
        # Reset any such rows to 'error' so the frontend reflects reality.
        try:
            from sqlalchemy import update
            from app.models.knowledge import KnowledgeDocument

            result = await db.execute(
                update(KnowledgeDocument)
                .where(KnowledgeDocument.status == "processing")
                .values(status="error")
            )
            orphan_count = result.rowcount
            if orphan_count:
                import logging

                logging.getLogger(__name__).warning(
                    "Recovered %d orphaned document(s): status reset from "
                    "'processing' to 'error' (ingestion task lost on restart).",
                    orphan_count,
                )
            await db.commit()
        except Exception:
            pass

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
app.include_router(project_router)


# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health_check():
    """Simple liveness probe for Docker / orchestrators."""
    return {"status": "ok"}
