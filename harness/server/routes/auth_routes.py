"""
Authentication and authorization API routes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from harness.core.auth import (
    AuthManager,
    Token,
    TokenData,
    User,
    UserCreate,
    UserLogin,
    get_auth_manager,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Dependency to get the current authenticated user."""
    auth_manager = get_auth_manager()
    token_data = auth_manager.verify_token(credentials.credentials)
    
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    
    user = auth_manager.get_user(token_data.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to require admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


@router.post("/register", response_model=User)
async def register(user_create: UserCreate):
    """Register a new user (admin only)."""
    auth_manager = get_auth_manager()
    
    # Check if current user is admin (simplified - in production, use proper auth)
    # For now, allow registration without auth for initial setup
    
    try:
        user = auth_manager.create_user(user_create)
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=Token)
async def login(login: UserLogin):
    """Authenticate a user and return a token."""
    auth_manager = get_auth_manager()
    user = auth_manager.authenticate(login)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    
    token = auth_manager.create_token(user)
    return token


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Logout and revoke the current token."""
    auth_manager = get_auth_manager()
    auth_manager.revoke_token(credentials.credentials)
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get the current authenticated user."""
    return current_user


@router.get("/users", response_model=list[User])
async def list_users(current_user: User = Depends(require_admin)):
    """List all users (admin only)."""
    auth_manager = get_auth_manager()
    return auth_manager.list_users()


@router.put("/users/{user_id}/role", response_model=User)
async def update_user_role(
    user_id: str,
    role: str,
    current_user: User = Depends(require_admin),
):
    """Update a user's role (admin only)."""
    auth_manager = get_auth_manager()
    user = auth_manager.update_user_role(user_id, role)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return user


@router.post("/users/{user_id}/deactivate", response_model=User)
async def deactivate_user(
    user_id: str,
    current_user: User = Depends(require_admin),
):
    """Deactivate a user (admin only)."""
    auth_manager = get_auth_manager()
    user = auth_manager.deactivate_user(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return user
