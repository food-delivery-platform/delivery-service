import os
import sys

from loguru import logger

_ALLOWED_LEVELS = {
    "TRACE",
    "DEBUG",
    "INFO",
    "SUCCESS",
    "WARNING",
    "ERROR",
    "CRITICAL",
}

_log_level = os.getenv("LOG_LEVEL", "INFO").upper().strip()
if _log_level not in _ALLOWED_LEVELS:
    _log_level = "INFO"

# Windows' default console code page (e.g. cp1251) can't encode arrows/em-dashes used in log
# messages elsewhere in this codebase — reconfigure to UTF-8 so loguru doesn't fail to emit them.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logger.remove()
logger.add(
    sys.stdout,
    level=_log_level,
    backtrace=True,
    diagnose=False,
)

__all__ = ["logger"]
