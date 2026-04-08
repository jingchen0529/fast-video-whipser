import logging
import os
import sys
from typing import Optional, Union

from concurrent_log_handler import ConcurrentRotatingFileHandler

from app.core.config import settings


def _resolve_log_level(log_level: Optional[Union[int, str]]) -> int:
    if log_level is None:
        log_level = settings.log_level

    if isinstance(log_level, int):
        return log_level

    resolved = getattr(logging, str(log_level).upper(), None)
    if isinstance(resolved, int):
        return resolved

    raise ValueError(f"Unsupported log level: {log_level}")


def configure_logging(
    name: Optional[str] = None,
    log_level: Optional[Union[int, str]] = None,
    log_dir: Optional[str] = None,
    log_file_prefix: Optional[str] = None,
    backup_count: Optional[int] = None,
    encoding: Optional[str] = None,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(_resolve_log_level(log_level))
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    resolved_log_dir = os.path.abspath(log_dir or settings.log_dir)
    os.makedirs(resolved_log_dir, exist_ok=True)

    resolved_log_file_prefix = (
        settings.log_file_prefix if log_file_prefix is None else log_file_prefix
    )
    resolved_backup_count = (
        settings.log_backup_count if backup_count is None else backup_count
    )
    resolved_encoding = settings.log_encoding if encoding is None else encoding

    if resolved_log_file_prefix:
        log_file_name = f"{resolved_log_file_prefix}.log"
        log_file_path = os.path.join(resolved_log_dir, log_file_name)
        rotating_file_handler = ConcurrentRotatingFileHandler(
            filename=log_file_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=resolved_backup_count,
            encoding=resolved_encoding,
        )
        rotating_file_handler.setFormatter(formatter)
        logger.addHandler(rotating_file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


__all__ = ["configure_logging"]
