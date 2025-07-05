"""
Logging Middleware - Logs HTTP requests and responses
"""

import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = structlog.get_logger()


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        logger.info(
            "Request started",
            method=request.method,
            url=str(request.url),
            request_id=getattr(request.state, "request_id", None),
        )

        response = await call_next(request)

        process_time = time.time() - start_time

        logger.info(
            "Request completed",
            method=request.method,
            url=str(request.url),
            status_code=response.status_code,
            process_time=process_time,
            request_id=getattr(request.state, "request_id", None),
        )

        return response
