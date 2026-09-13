"""
Application-wide logging configuration.

Configures the root logger once, at process startup, so every module's
`logging.getLogger(__name__)` calls inherit consistent formatting and level
instead of each module reaching for its own ad-hoc `basicConfig`.

Never log credentials, tokens, or full connection strings — settings.py
builds the database/Redis URLs on demand and nothing in this codebase
logs them directly; keep it that way.
"""
import logging
import sys

from app.core.config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging() -> None:
    level = logging.DEBUG if settings.DEBUG else logging.INFO
    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        stream=sys.stdout,
        force=True,  # override any handlers a dependency installed on import
    )
    if not settings.DEBUG:
        # SQLAlchemy's engine logger is noisy (echoes SQL) at INFO — keep it
        # quiet unless someone is actively debugging locally.
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
