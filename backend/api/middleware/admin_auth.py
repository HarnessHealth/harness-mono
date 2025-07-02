"""
Harness - Admin Authentication Middleware
Protects admin routes with JWT authentication and role-based access control
"""
from typing import Optional, Callable
from functools import wraps
import jwt
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timezone

from backend.core.config import settings
from backend.models.user import User, UserRole


security = HTTPBearer()


class AdminAuth:
    """Admin authentication handler"""
    
    def __init__(self, secret_key: str = None):
        self.secret_key = secret_key or settings.SECRET_KEY
        self.algorithm = "HS256"
    
    async def verify_token(self, credentials: HTTPAuthorizationCredentials) -> dict:
        """Verify JWT token and extract claims"""
        token = credentials.credentials
        
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            
            # Check token expiration
            exp = payload.get("exp")
            if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has expired"
                )
            
            return payload
            
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token"
            )
    
    async def get_current_user(self, request: Request, credentials: HTTPAuthorizationCredentials) -> User:
        """Get current user from token"""
        payload = await self.verify_token(credentials)
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )
        
        # Get user from database (simplified for now)
        # In production, this would query the actual database
        user = User(
            id=user_id,
            email=payload.get("email"),
            role=UserRole(payload.get("role", "viewer"))
        )
        
        return user
    
    def require_admin(self, func: Callable) -> Callable:
        """Decorator to require admin role"""
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            credentials = await security(request)
            user = await self.get_current_user(request, credentials)
            
            if user.role != UserRole.ADMIN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin access required"
                )
            
            # Add user to request state
            request.state.user = user
            return await func(request, *args, **kwargs)
        
        return wrapper
    
    def require_auth(self, min_role: UserRole = UserRole.VIEWER) -> Callable:
        """Decorator to require minimum role"""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(request: Request, *args, **kwargs):
                credentials = await security(request)
                user = await self.get_current_user(request, credentials)
                
                # Check role hierarchy
                role_hierarchy = {
                    UserRole.VIEWER: 0,
                    UserRole.USER: 1,
                    UserRole.ADMIN: 2
                }
                
                if role_hierarchy.get(user.role, 0) < role_hierarchy.get(min_role, 0):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Minimum role required: {min_role.value}"
                    )
                
                request.state.user = user
                return await func(request, *args, **kwargs)
            
            return wrapper
        return decorator


# Global admin auth instance
admin_auth = AdminAuth()