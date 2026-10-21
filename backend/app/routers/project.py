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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.knowledge import KnowledgeDocument
from app.models.project import Project
from app.models.user import User
from app.schemas.project import (
    ProjectDocumentRef,
    ProjectListResponse,
    ProjectResponse,
    ReviewSummaryRequest,
)
from app.services.analysis import analyze_project_background
from app.services.uploads import save_upload, upload_dir
from app.services.vectorization import ingest_documents

router = APIRouter(prefix="/projects", tags=["projects"])

# ── Helpers ───────────────────────────────────────────────────────────────────


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
        status=_derive_project_status([doc.status for doc in docs]),
        documents=docs,
        created_at=project.created_at,
        created_by_name=project.creator.full_name if project.creator else None,
        analysis_result=project.analysis_result,
        analysis_status=project.analysis_status or (
            "completed" if project.analysis_result else "idle"
        ),
        analysis_error=project.analysis_error,
        review_summary=project.review_summary,
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
    background_tasks: BackgroundTasks,
    file1: UploadFile | None = None,
    file2: UploadFile | None = None,
    file3: UploadFile | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload 1-3 documents and group them into a project for AI analysis.

    Each provided file is saved to disk, stored as a KnowledgeDocument, and
    queued for async chunking and embedding (same pipeline as
    ``POST /knowledge/upload``).  The project status is ``"indexing"`` until
    all documents finish ingestion.
    """
    files: list[UploadFile] = [f for f in (file1, file2, file3) if f is not None]

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file is required (file1, file2, or file3).",
        )

    doc_rows: list[KnowledgeDocument] = []
    try:
        for file in files:
            doc_rows.append(await save_upload(file, current_user.id, "private"))

        db.add_all(doc_rows)
        await db.flush()
        for d in doc_rows:
            await db.refresh(d)

        project = Project(
            created_by=current_user.id,
            document_ids=[d.id for d in doc_rows],
            status="indexing",
        )
        db.add(project)
        await db.flush()
        await db.refresh(project)
        await db.commit()
    except BaseException:
        for doc in doc_rows:
            (upload_dir() / doc.file_path).unlink(missing_ok=True)
        raise

    background_tasks.add_task(
        ingest_documents,
        [(d.id, upload_dir() / d.file_path, d.file_type) for d in doc_rows],
    )

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
    if project.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own projects.",
        )

    # Resolve current per-document statuses from KnowledgeDocument rows
    doc_refs = await _resolve_documents(db, project.document_ids)
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
        project_responses.append(_project_to_response(p, doc_refs))

    return ProjectListResponse(projects=project_responses, total=total)


# ═══════════════════════════════════════════════════════════════════════════════
#  DELETE /projects/{project_id}/documents/{document_id}
# ═══════════════════════════════════════════════════════════════════════════════


@router.delete(
    "/{project_id}/documents/{document_id}",
    summary="Remove a document from a project",
)
async def remove_project_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a document from a project — removes from disk and pgvector,
    and updates the project's document list.  Returns the updated project.
    If the last document is removed, the project itself is deleted."""
    # 1. Fetch project & verify ownership
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    if project.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only modify your own projects.",
        )

    # 2. Verify the document belongs to this project
    if document_id not in project.document_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found in this project.",
        )

    # 3. Fetch the KnowledgeDocument to get disk path
    doc_result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
    )
    doc = doc_result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    # 4. Remove file from disk (best-effort)
    disk_path = upload_dir() / doc.file_path
    try:
        disk_path.unlink(missing_ok=True)
    except OSError:
        pass

    # 5. Delete the KnowledgeDocument (cascade-deletes chunks in pgvector)
    await db.delete(doc)

    # 6. Update project's document_ids array
    new_ids = [did for did in project.document_ids if did != document_id]

    if not new_ids:
        # Last document removed — delete the whole project
        await db.delete(project)
        await db.commit()
        return JSONResponse(
            status_code=200,
            content={
                "deleted": True,
                "message": "Project deleted (no documents remaining).",
            },
        )

    project.document_ids = new_ids
    project.status = _derive_project_status(
        [d.status for d in await _resolve_documents(db, new_ids)]
    )
    await db.commit()
    await db.refresh(project)

    # 7. Return updated project
    doc_refs = await _resolve_documents(db, project.document_ids)
    return _project_to_response(project, doc_refs)


# ═══════════════════════════════════════════════════════════════════════════════
#  POST /projects/{project_id}/analyze
# ═══════════════════════════════════════════════════════════════════════════════


@router.post(
    "/{project_id}/analyze",
    response_model=ProjectResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start AI extraction on a project's documents",
)
async def analyze_project(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start analysis and return immediately; poll GET /projects/{id} for status."""
    # 1. Fetch project and verify ownership
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    # Verify ownership — only the creator can analyse their project
    if project.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to analyse this project.",
        )

    # Check document status before starting new work.
    doc_refs = await _resolve_documents(db, project.document_ids)
    if project.analysis_status == "running" or (
        not force and project.analysis_result is not None
    ):
        return _project_to_response(project, doc_refs)

    unindexed = [d for d in doc_refs if d.status != "indexed"]
    if unindexed:
        names = ", ".join(f"'{d.filename}' ({d.status})" for d in unindexed)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot analyse project — {len(unindexed)} document(s) still "
                f"processing: {names}.  Wait for ingestion to complete and try again."
            ),
        )

    # Claim the project once, including when two tabs start analysis together.
    claimed = await db.execute(
        update(Project)
        .where(Project.id == project_id, Project.analysis_status != "running")
        .values(analysis_status="running", analysis_error=None)
    )
    await db.commit()
    if claimed.rowcount:
        background_tasks.add_task(
            analyze_project_background, project_id, list(project.document_ids), force
        )
    await db.refresh(project)
    return _project_to_response(project, doc_refs)


# ═══════════════════════════════════════════════════════════════════════════════
#  PUT /projects/{project_id}/review
# ═══════════════════════════════════════════════════════════════════════════════


@router.put(
    "/{project_id}/review",
    response_model=ProjectResponse,
    summary="Save the user-reviewed project action summary",
)
async def save_review(
    project_id: uuid.UUID,
    body: ReviewSummaryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Persist the user's reviewed action summary (facts with classifications,
    conflicts with resolution notes, and action items with approve/reject
    decisions).  Overwrites any previously saved review.

    Returns 404 if the project doesn't exist, 403 if the caller isn't the
    creator, and 409 if no analysis has been run yet.
    """
    # 1. Fetch project and verify ownership
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    if project.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only save reviews for your own projects.",
        )
    if project.analysis_status == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wait for the current analysis to finish before saving a review.",
        )

    # 2. Ensure an analysis exists before allowing a review save
    if project.analysis_result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot save review — run analysis first.",
        )

    # 3. Persist the review summary
    project.review_summary = body.model_dump()
    await db.flush()

    # 4. Return updated project
    doc_refs = await _resolve_documents(db, project.document_ids)
    return _project_to_response(project, doc_refs)
