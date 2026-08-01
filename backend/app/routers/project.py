# ── Project Router ────────────────────────────────────────────────────────────
# Endpoints for creating and listing multi-document projects.
# A project groups 1-3 uploaded KnowledgeDocuments so the AI pipeline can
# analyse them together (cross-document conflict detection, etc.).
#
# Design:
#   • POST /projects — multipart upload with file1/file2/file3 (at least 1).
#     Each file is saved to disk, a KnowledgeDocument row is created, and
#     ingestion is fired in the background (same pattern as /knowledge/upload).
#     A Project row links all the doc IDs.
#   • GET /projects/{id} — returns project with per-document statuses,
#     derived aggregate status, and creator info.
#   • GET /projects — paginated list of the current user's projects.

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models.knowledge import KnowledgeDocument
from app.models.project import Project
from app.models.user import User
from app.schemas.project import (
    ProjectDocumentRef,
    ProjectListResponse,
    ProjectResponse,
)

router = APIRouter(prefix="/projects", tags=["projects"])

# ── Helpers (reuse patterns from knowledge router) ────────────────────────────


def _validate_ext(filename: str) -> str:
    """Return the lowercase extension without dot if allowed, else raise 400."""
    ext = Path(filename).suffix.lower()
    if ext not in settings.allowed_upload_extensions_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"File type '{ext}' is not allowed. "
                f"Accepted: {', '.join(sorted(settings.allowed_upload_extensions_set))}"
            ),
        )
    return ext


def _upload_dir() -> Path:
    """Return the absolute upload directory, creating it if needed."""
    path = Path(settings.UPLOAD_DIR).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _derive_project_status(doc_statuses: list[str]) -> str:
    """Derive aggregate project status from individual document statuses.

    Rules:
        any "processing" → "indexing"
        any "error"      → "error"
        all "indexed"    → "ready"
    """
    if any(s == "processing" for s in doc_statuses):
        return "indexing"
    if any(s == "error" for s in doc_statuses):
        return "error"
    return "ready"


async def _resolve_documents(
    db: AsyncSession, doc_ids: list[uuid.UUID]
) -> list[ProjectDocumentRef]:
    """Fetch KnowledgeDocument rows by IDs and return ProjectDocumentRef list."""
    if not doc_ids:
        return []
    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id.in_(doc_ids))
    )
    docs = result.scalars().all()
    # Preserve project's original insertion order (not DB order)
    docs_by_id = {d.id: d for d in docs}
    return [
        ProjectDocumentRef(
            id=did,
            filename=docs_by_id[did].filename,
            file_type=docs_by_id[did].file_type,
            file_size=docs_by_id[did].file_size,
            status=docs_by_id[did].status,
        )
        for did in doc_ids
        if did in docs_by_id
    ]


def _project_to_response(
    project: Project, docs: list[ProjectDocumentRef]
) -> ProjectResponse:
    """Map ORM project + resolved docs to the Pydantic response schema."""
    return ProjectResponse(
        id=project.id,
        status=project.status,
        documents=docs,
        created_at=project.created_at,
        created_by_name=project.creator.full_name if project.creator else None,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  POST /projects
# ═══════════════════════════════════════════════════════════════════════════════


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project with 1-3 uploaded documents",
)
async def create_project(
    file1: UploadFile | None = None,
    file2: UploadFile | None = None,
    file3: UploadFile | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload 1-3 documents and group them into a project for AI analysis.

    Each provided file is saved to disk, stored as a KnowledgeDocument, and
    queued for async chunking/embedding/FAISS-indexing (same pipeline as
    ``POST /knowledge/upload``).  The project status is ``"indexing"`` until
    all documents finish ingestion.
    """
    files: list[UploadFile] = [f for f in (file1, file2, file3) if f is not None]

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file is required (file1, file2, or file3).",
        )

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    upload_dir = _upload_dir()
    doc_rows: list[KnowledgeDocument] = []

    for f in files:
        # Validate
        if not f.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All files must have a filename.",
            )
        _validate_ext(f.filename)

        # Read content
        content = await f.read()
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"File '{f.filename}' exceeds maximum size of "
                    f"{settings.MAX_UPLOAD_SIZE_MB} MB."
                ),
            )

        # Save to disk with UUID-safe name
        ext = Path(f.filename).suffix.lower()
        stored_name = f"{uuid.uuid4().hex}{ext}"
        disk_path = upload_dir / stored_name
        disk_path.write_bytes(content)

        # Create KnowledgeDocument row
        doc = KnowledgeDocument(
            filename=f.filename,
            file_type=ext.lstrip("."),
            file_path=stored_name,
            file_size=len(content),
            uploaded_by=current_user.id,
            status="processing",
        )
        doc_rows.append(doc)

    # Bulk-persist all KnowledgeDocument rows
    db.add_all(doc_rows)
    await db.flush()
    # Refresh all to get their IDs populated
    for d in doc_rows:
        await db.refresh(d)

    # Create the Project row linking all document UUIDs
    project = Project(
        created_by=current_user.id,
        document_ids=[d.id for d in doc_rows],
        status="indexing",
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)

    # Commit now so the background tasks can see these rows in their sessions
    await db.commit()

    # Fire async ingestion for each document (same pattern as /knowledge/upload)
    import asyncio
    from app.services.vectorization import ingest_document

    async def _safe_ingest(doc: KnowledgeDocument, path: Path) -> None:
        try:
            await ingest_document(
                doc_id=doc.id, file_path=path, file_type=doc.file_type
            )
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "Background ingestion failed for document %s",
                doc.id,
            )

    for d in doc_rows:
        asyncio.create_task(_safe_ingest(d, upload_dir / d.file_path))

    # Build response from the already-fetched doc rows
    doc_refs = [
        ProjectDocumentRef(
            id=d.id,
            filename=d.filename,
            file_type=d.file_type,
            file_size=d.file_size,
            status=d.status,
        )
        for d in doc_rows
    ]
    return _project_to_response(project, doc_refs)


# ═══════════════════════════════════════════════════════════════════════════════
#  GET /projects/{project_id}
# ═══════════════════════════════════════════════════════════════════════════════


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get a project with current document ingestion statuses",
)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the project with live per-document ingestion statuses.

    Used by the frontend to poll until all documents finish indexing.  The
    aggregate status is derived on each request (not cached in the DB) so
    the frontend always sees current state.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    # Resolve current per-document statuses from KnowledgeDocument rows
    doc_refs = await _resolve_documents(db, project.document_ids)
    project.status = _derive_project_status([d.status for d in doc_refs])

    return _project_to_response(project, doc_refs)


# ═══════════════════════════════════════════════════════════════════════════════
#  GET /projects
# ═══════════════════════════════════════════════════════════════════════════════


@router.get(
    "",
    response_model=ProjectListResponse,
    summary="List projects created by the current user",
)
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 50,
):
    """Return a paginated list of the current user's projects, newest first."""
    total_result = await db.execute(
        select(func.count(Project.id)).where(Project.created_by == current_user.id)
    )
    total = total_result.scalar_one()

    result = await db.execute(
        select(Project)
        .where(Project.created_by == current_user.id)
        .order_by(Project.created_at.desc())
        .offset(skip)
        .limit(limit),
    )
    projects = result.scalars().all()

    project_responses: list[ProjectResponse] = []
    for p in projects:
        doc_refs = await _resolve_documents(db, p.document_ids)
        p.status = _derive_project_status([d.status for d in doc_refs])
        project_responses.append(_project_to_response(p, doc_refs))

    return ProjectListResponse(projects=project_responses, total=total)
