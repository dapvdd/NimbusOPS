"""DB session dependency re-export for API modules."""

from ..core.db import get_db

__all__ = ["get_db"]
