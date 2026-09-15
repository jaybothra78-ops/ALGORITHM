"""Authentication endpoints and user session dependency for multi-user terminal."""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel, Field
from db.user_repository import UserRepository


router = APIRouter(prefix="/auth", tags=["User Authentication"])


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    password: str = Field(..., min_length=4, max_length=100, description="Password")
    display_name: str | None = Field(default=None, max_length=100, description="Optional display name")


class LoginRequest(BaseModel):
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


def get_current_user(authorization: str | None = Header(None)) -> dict[str, Any]:
    """Dependency to retrieve the active user from session token, falling back to default user if unauthenticated."""
    if authorization:
        parts = authorization.split()
        token = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else authorization.strip()
        user = UserRepository.get_user_by_session(token)
        if user:
            return user
        raise HTTPException(status_code=401, detail="Invalid or expired session token")

    # Fallback to default user 1 for headless calls and test suites
    default_user = UserRepository.get_user_by_id(1)
    if default_user:
        return default_user
    return {"id": 1, "username": "trader", "display_name": "Default Trader"}


@router.post("/register", response_model=dict[str, Any])
def register_endpoint(payload: RegisterRequest) -> dict[str, Any]:
    """Register a new user, create their virtual portfolio, and return a session token."""
    try:
        user = UserRepository.create_user(
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
        )
        token = UserRepository.create_session(user["id"])
        return {
            "success": True,
            "token": token,
            "user": user,
            "message": f"Account '{user['username']}' created successfully.",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Registration failed: {exc}") from exc


@router.post("/login", response_model=dict[str, Any])
def login_endpoint(payload: LoginRequest) -> dict[str, Any]:
    """Authenticate user credentials and issue a session token."""
    user = UserRepository.authenticate_user(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = UserRepository.create_session(user["id"])
    return {
        "success": True,
        "token": token,
        "user": user,
        "message": f"Welcome back, {user['display_name']}!",
    }


@router.post("/logout", response_model=dict[str, Any])
def logout_endpoint(authorization: str | None = Header(None)) -> dict[str, Any]:
    """Invalidate current session token."""
    if authorization:
        parts = authorization.split()
        token = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else authorization.strip()
        UserRepository.delete_session(token)
    return {"success": True, "message": "Logged out successfully"}


@router.get("/me", response_model=dict[str, Any])
def get_me_endpoint(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Return currently active user profile and account details."""
    from services.paper_service import PaperTradingService
    summary = PaperTradingService.get_summary(user_id=user["id"])
    return {
        "user": user,
        "portfolio": summary.model_dump(),
    }


@router.get("/users", response_model=list[dict[str, Any]])
def list_users_endpoint() -> list[dict[str, Any]]:
    """Return list of local users for fast terminal user switching."""
    return UserRepository.list_users()
