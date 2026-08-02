import asyncio
from app.database import AsyncSessionLocal
from app.models.project import Project
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Project).limit(1))
        project = result.scalar_one_or_none()
        if project:
            print("Before:", project.review_summary)
            project.review_summary = {"facts": [{"content": "test edit"}]}
            await session.commit()
            print("Committed")

        result = await session.execute(select(Project).limit(1))
        project2 = result.scalar_one_or_none()
        if project2:
            print("After:", project2.review_summary)

asyncio.run(main())
