# ── Models Package ────────────────────────────────────────────────────────────
# Import all ORM models here so Alembic's autogenerate can detect them.

from app.models.knowledge import DocumentChunk, KnowledgeDocument  # noqa: F401
from app.models.user import TokenBlacklist, User  # noqa: F401
