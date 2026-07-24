"""Import every module's models so Alembic autogenerate sees them.

A model missing from this file will be ABSENT from migrations and
autogenerate may emit a DROP for its table. One line per module.
"""

from app.db.base import Base  # noqa: F401
from app.modules.identity import models as identity_models  # noqa: F401

__all__ = ["Base"]
