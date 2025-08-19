"""Logging utilities for GitLab Migration Tool."""

import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def setup_logging(
    level: str = 'INFO',
    log_file: Optional[str] = None,
    log_format: Optional[str] = None,
) -> None:
    """Setup logging configuration using loguru.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path
        log_format: Optional custom log format
    """
    # Remove default handler
    logger.remove()

    # Default format if not provided
    if log_format is None:
        log_format = (
            '<green>{time:YYYY-MM-DD HH:mm:ss}</green> | '
            '<level>{level: <8}</level> | '
            '<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | '
            '<level>{message}</level>'
        )

    # Add console handler
    logger.add(
        sys.stderr,
        format=log_format,
        level=level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # Add file handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # File format (no colors)
        file_format = (
            '{time:YYYY-MM-DD HH:mm:ss} | '
            '{level: <8} | '
            '{name}:{function}:{line} | '
            '{message}'
        )

        logger.add(
            log_file,
            format=file_format,
            level=level,
            rotation='10 MB',
            retention='30 days',
            compression='gz',
            backtrace=True,
            diagnose=True,
        )

    logger.info(f'Logging initialized with level: {level}')
    if log_file:
        logger.info(f'Log file: {log_file}')


def get_logger(name: str):
    """Get a logger instance with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logger.bind(name=name)
