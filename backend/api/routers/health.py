"""
Health check endpoints for Harness API
"""
from typing import Dict, Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from backend.api.config import settings
from backend.models.database import get_db

router = APIRouter()


@router.get("/")
async def health_check() -> Dict[str, str]:
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "service": "Harness API",
        "version": settings.APP_VERSION,
    }


@router.get("/ready")
async def readiness_check(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Readiness check that verifies all dependencies are available.
    Used by Kubernetes readiness probes.
    """
    checks = {
        "api": True,
        "database": False,
        "redis": False,
        "weaviate": False,
    }
    
    # Check database
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        pass
    
    # Check Redis
    try:
        r = redis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        checks["redis"] = True
    except Exception:
        pass
    
    # Check if all services are ready
    all_ready = all(checks.values())
    
    return {
        "ready": all_ready,
        "checks": checks,
        "version": settings.APP_VERSION,
    }


@router.get("/live")
async def liveness_check() -> Dict[str, str]:
    """
    Liveness check endpoint.
    Used by Kubernetes liveness probes.
    """
    return {
        "status": "alive",
        "service": "Harness API",
    }