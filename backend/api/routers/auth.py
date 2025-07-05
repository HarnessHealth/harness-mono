"""
Harness - Auth API Router
Provides authentication endpoints
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/")
async def auth_placeholder():
    """Placeholder for auth endpoint"""
    return {"message": "Auth service coming soon"}
