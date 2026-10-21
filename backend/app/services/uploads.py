"""Shared file validation and storage for knowledge and project uploads."""

import uuid
from pathlib import Path

import aiofiles
from fastapi import HTTPException, UploadFile, status

from app.config import settings
from app.models.knowledge import KnowledgeDocument


def upload_dir() -> Path:
    path = Path(settings.UPLOAD_DIR).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_upload(
    file: UploadFile, user_id: uuid.UUID, visibility: str
) -> KnowledgeDocument:
    """Validate an uploaded file, save it, and return its unpersisted row."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    extension = Path(file.filename).suffix.lower()
    if extension not in settings.allowed_upload_extensions_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"File type '{extension}' is not allowed. Accepted: "
                f"{', '.join(sorted(settings.allowed_upload_extensions_set))}"
            ),
        )

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    stored_name = f"{uuid.uuid4().hex}{extension}"
    path = upload_dir() / stored_name
    size = 0
    try:
        async with aiofiles.open(path, "wb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"File '{file.filename}' exceeds maximum size of {settings.MAX_UPLOAD_SIZE_MB} MB.",
                    )
                await destination.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return KnowledgeDocument(
        filename=file.filename,
        file_type=extension.lstrip("."),
        file_path=stored_name,
        file_size=size,
        uploaded_by=user_id,
        status="processing",
        visibility=visibility,
    )
