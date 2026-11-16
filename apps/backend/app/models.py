"""Import every module's models here so Alembic and the metadata see them."""

from app.core.database import Base

__all__ = ["Base"]
