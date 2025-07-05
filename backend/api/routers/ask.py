"""
Harness - Ask API Router
Provides endpoints for the ask service
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/ask", tags=["ask"])


@router.get("/")
async def ask_placeholder():
    """Placeholder for ask endpoint"""
    return {"message": "Ask service coming soon"}
