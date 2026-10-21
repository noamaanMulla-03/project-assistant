"""Shared upload validation and storage checks."""

import io
import uuid

import pytest
from fastapi import HTTPException, UploadFile

from app.config import settings
from app.services.uploads import save_upload


@pytest.mark.asyncio
async def test_save_upload_stores_file_and_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    user_id = uuid.uuid4()
    file = UploadFile(filename="policy.TXT", file=io.BytesIO(b"policy text"))

    doc = await save_upload(file, user_id, "public")

    assert doc.file_type == "txt"
    assert doc.visibility == "public"
    assert doc.uploaded_by == user_id
    assert (tmp_path / doc.file_path).read_bytes() == b"policy text"


@pytest.mark.asyncio
async def test_save_upload_rejects_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    file = UploadFile(filename="bad.exe", file=io.BytesIO(b"no"))

    with pytest.raises(HTTPException) as exc:
        await save_upload(file, uuid.uuid4(), "private")

    assert exc.value.status_code == 400
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_save_upload_rejects_oversized_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    file = UploadFile(filename="large.txt", file=io.BytesIO(b"x" * (1024 * 1024 + 1)))

    with pytest.raises(HTTPException) as exc:
        await save_upload(file, uuid.uuid4(), "public")

    assert exc.value.status_code == 413
    assert not list(tmp_path.iterdir())
