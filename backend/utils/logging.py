"""
Logging utility for Harness
"""

import logging
import sys


def setup_logging(
    level: str = "INFO",
    format_string: str | None = None,
    include_timestamp: bool = True,
) -> None:
    """
    Setup logging configuration for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Custom format string for log messages
        include_timestamp: Whether to include timestamp in log messages
    """
    # Default format string
    if format_string is None:
        if include_timestamp:
            format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        else:
            format_string = "%(name)s - %(levelname)s - %(message)s"

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=format_string,
        stream=sys.stdout,
        force=True,
    )

    # Set specific loggers
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)
