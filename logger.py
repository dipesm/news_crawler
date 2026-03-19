# =============================================================================
# logger.py — Centralized logging (file + console)
# =============================================================================

import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from config import LOG_DIR, LOG_LEVEL, LOG_RETENTION_DAYS

os.makedirs(LOG_DIR, exist_ok=True)

def get_logger(name: str) -> logging.Logger:
    """
    Return a logger that writes to both console and a dated log file.
    Each module gets its own logger name for easy filtering.

    Usage:
        from logger import get_logger
        log = get_logger(__name__)
        log.info("Starting scrape")
        log.warning("Selector not found")
        log.error("Site failed: %s", error)
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # already configured

    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    formatter = logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8s  %(name)-30s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # --- Console handler ---
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    # --- File handler (rotates daily, keeps LOG_RETENTION_DAYS files) ---
    log_file = os.path.join(LOG_DIR, f"scraper_{datetime.now():%Y-%m-%d}.log")
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        backupCount=LOG_RETENTION_DAYS,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
