"""
Harness API - Main FastAPI Application
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
# from strawberry.fastapi import GraphQLRouter

from backend.api.config import settings
# from backend.api.graphql.schema import schema
from backend.api.middleware import (
    RequestIDMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware,
)
from backend.api.routers import health, ask, auth, admin
from backend.utils.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Handle application startup and shutdown events."""
    # Startup
    setup_logging()
    # Initialize database connections, cache, etc.
    yield
    # Shutdown - cleanup connections


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Harness API",
        description="Veterinary Clinical AI Platform - Ask and Diagnose Services",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # Add middleware
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # Add REST API routers
    app.include_router(health.router, prefix="/api/health", tags=["health"])
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(ask.router, prefix="/api/ask", tags=["ask"])
    app.include_router(admin.router, tags=["admin"])

    # Add GraphQL endpoint (temporarily disabled)
    # graphql_app = GraphQLRouter(schema)
    # app.include_router(graphql_app, prefix="/graphql")

    return app


app = create_app()