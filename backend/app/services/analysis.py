"""Run a bounded number of project analyses outside HTTP requests."""

import asyncio
import logging
from uuid import UUID

from sqlalchemy import update

from app.database import AsyncSessionLocal
from app.models.project import Project
from app.services.extraction import run_extraction

logger = logging.getLogger(__name__)
_analysis_slots = asyncio.Semaphore(2)


async def analyze_project_background(
    project_id: UUID, document_ids: list[UUID], force: bool
) -> None:
    try:
        async with _analysis_slots:
            async with AsyncSessionLocal() as db:
                result = await run_extraction(db, document_ids)

            values = {
                "analysis_result": result.model_dump(),
                "analysis_status": "completed",
                "analysis_error": None,
            }
            if force:
                values["review_summary"] = None
            async with AsyncSessionLocal() as db:
                await db.execute(update(Project).where(Project.id == project_id).values(**values))
                await db.commit()
    except asyncio.CancelledError:
        await _record_error(project_id, "Analysis was interrupted. Please retry.")
        raise
    except Exception as exc:
        logger.exception("Analysis failed for project %s", project_id)
        await _record_error(project_id, str(exc)[:1000])


async def _record_error(project_id: UUID, message: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(analysis_status="error", analysis_error=message)
        )
        await db.commit()
