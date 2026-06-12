"""
Authentication and authorization API routes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from harness.data.db import get_session
from harness.core.auth import (
    Token,
    User,
    UserCreate,
    UserLogin,
    get_auth_manager,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_session),
) -> User:
    """Dependency to get the current authenticated user."""
    auth_manager = get_auth_manager()
    token_data = auth_manager.verify_token(credentials.credentials)
    
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    
    user = await auth_manager.get_user(db, token_data.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    
    return User.from_orm(user)


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to require admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


@router.post("/register", response_model=User)
async def register(
    user_create: UserCreate,
    db: AsyncSession = Depends(get_session),
):
    """Register a new user."""
    auth_manager = get_auth_manager()
    
    try:
        user = await auth_manager.create_user(db, user_create)
        return User.from_orm(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=Token)
async def login(
    login: UserLogin,
    db: AsyncSession = Depends(get_session),
):
    """Authenticate a user and return a token."""
    auth_manager = get_auth_manager()
    user = await auth_manager.authenticate(db, login)
    
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
async def list_users(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """List all users (admin only)."""
    auth_manager = get_auth_manager()
    users = await auth_manager.list_users(db)
    return [User.from_orm(u) for u in users]


@router.put("/users/{user_id}/role", response_model=User)
async def update_user_role(
    user_id: str,
    role: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Update a user's role (admin only)."""
    auth_manager = get_auth_manager()
    user = await auth_manager.update_user_role(db, user_id, role)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return User.from_orm(user)


@router.post("/users/{user_id}/deactivate", response_model=User)
async def deactivate_user(
    user_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Deactivate a user (admin only)."""
    auth_manager = get_auth_manager()
    user = await auth_manager.deactivate_user(db, user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return User.from_orm(user)
