"""
Authentication and authorization module for VLoop Harness.

Supports multi-user authentication with JWT tokens and role-based access control.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel


class User(BaseModel):
    """User model."""
    
    id: str
    username: str
    email: str
    role: str = "user"  # admin, user, readonly
    created_at: datetime
    is_active: bool = True


class UserCreate(BaseModel):
    """User creation request."""
    
    username: str
    email: str
    password: str
    role: str = "user"


class UserLogin(BaseModel):
    """User login request."""
    
    username: str
    password: str


class Token(BaseModel):
    """JWT token response."""
    
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    """Token data payload."""
    
    user_id: str
    username: str
    role: str
    exp: datetime


class AuthManager:
    """Manages user authentication and authorization."""
    
    def __init__(self):
        self._users: dict[str, User] = {}
        self._password_hashes: dict[str, str] = {}
        self._tokens: dict[str, TokenData] = {}
        self._secret_key = secrets.token_urlsafe(32)
        
        # Create default admin user
        self._create_default_admin()
    
    def _create_default_admin(self) -> None:
        """Create default admin user if none exists."""
        admin_id = "admin"
        if admin_id not in self._users:
            admin = User(
                id=admin_id,
                username="admin",
                email="admin@localhost",
                role="admin",
                created_at=datetime.now(timezone.utc),
                is_active=True,
            )
            password_hash = self._hash_password("admin123")  # Default password
            self._users[admin_id] = admin
            self._password_hashes[admin_id] = password_hash
    
    def _hash_password(self, password: str) -> str:
        """Hash a password using SHA-256."""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash."""
        return self._hash_password(password) == password_hash
    
    def create_user(self, user_create: UserCreate) -> User:
        """Create a new user."""
        # Check if username already exists
        for user in self._users.values():
            if user.username == user_create.username:
                raise ValueError(f"Username '{user_create.username}' already exists")
            if user.email == user_create.email:
                raise ValueError(f"Email '{user_create.email}' already exists")
        
        user_id = secrets.token_urlsafe(16)
        password_hash = self._hash_password(user_create.password)
        
        user = User(
            id=user_id,
            username=user_create.username,
            email=user_create.email,
            role=user_create.role,
            created_at=datetime.now(timezone.utc),
            is_active=True,
        )
        
        self._users[user_id] = user
        self._password_hashes[user_id] = password_hash
        
        return user
    
    def authenticate(self, login: UserLogin) -> Optional[User]:
        """Authenticate a user and return the user if valid."""
        for user_id, user in self._users.items():
            if user.username == login.username and user.is_active:
                password_hash = self._password_hashes.get(user_id)
                if password_hash and self._verify_password(login.password, password_hash):
                    return user
        return None
    
    def create_token(self, user: User, expires_in_hours: int = 24) -> Token:
        """Create a JWT token for a user."""
        exp = datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)
        
        # Simple token format (in production, use proper JWT library)
        token_data = TokenData(
            user_id=user.id,
            username=user.username,
            role=user.role,
            exp=exp,
        )
        
        # Create a simple token (in production, use proper JWT signing)
        token_str = self._encode_token(token_data)
        self._tokens[token_str] = token_data
        
        return Token(
            access_token=token_str,
            token_type="bearer",
            expires_in=int(expires_in_hours * 3600),
        )
    
    def _encode_token(self, token_data: TokenData) -> str:
        """Encode token data into a string (simplified)."""
        data_str = f"{token_data.user_id}:{token_data.username}:{token_data.role}:{token_data.exp.isoformat()}"
        signature = hashlib.sha256(f"{data_str}:{self._secret_key}".encode()).hexdigest()
        return f"{data_str}:{signature}"
    
    def verify_token(self, token: str) -> Optional[TokenData]:
        """Verify a token and return the token data if valid."""
        token_data = self._tokens.get(token)
        if not token_data:
            return None
        
        # Check expiration
        if token_data.exp < datetime.now(timezone.utc):
            del self._tokens[token]
            return None
        
        return token_data
    
    def revoke_token(self, token: str) -> None:
        """Revoke a token."""
        if token in self._tokens:
            del self._tokens[token]
    
    def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID."""
        return self._users.get(user_id)
    
    def list_users(self) -> list[User]:
        """List all users."""
        return list(self._users.values())
    
    def update_user_role(self, user_id: str, role: str) -> Optional[User]:
        """Update a user's role."""
        user = self._users.get(user_id)
        if user:
            user.role = role
            return user
        return None
    
    def deactivate_user(self, user_id: str) -> Optional[User]:
        """Deactivate a user."""
        user = self._users.get(user_id)
        if user:
            user.is_active = False
            # Revoke all tokens for this user
            tokens_to_revoke = [
                token for token, data in self._tokens.items()
                if data.user_id == user_id
            ]
            for token in tokens_to_revoke:
                del self._tokens[token]
            return user
        return None


# Global auth manager instance
_auth_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    """Get the global auth manager instance."""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager
