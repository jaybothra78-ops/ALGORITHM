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

    # Fallback to isolated guest user (id: 0) so unauthenticated calls NEVER access Jay's private data
    return {"id": 0, "username": "guest", "display_name": "Guest Trader"}


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
    clean_u = payload.username.strip().lower()
    if not UserRepository.user_exists(clean_u) and clean_u != "trader":
        raise HTTPException(
            status_code=401,
            detail=f"Account '{payload.username}' does not exist. Please click 'Create Account' to register your account.",
        )

    user = UserRepository.authenticate_user(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect password. Please verify your credentials and try again.")

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


class GoogleAuthRequest(BaseModel):
    credential: str = Field(..., description="Google ID Token / Credential")


@router.get("/google/config", response_model=dict[str, Any])
def google_config_endpoint() -> dict[str, Any]:
    """Return public Google OAuth client ID and activation status."""
    from core.config import settings
    client_id = settings.GOOGLE_CLIENT_ID.strip()
    return {
        "client_id": client_id,
        "enabled": bool(client_id),
    }


@router.post("/google", response_model=dict[str, Any])
def google_login_endpoint(payload: GoogleAuthRequest) -> dict[str, Any]:
    """Verify Google ID token, authenticate existing user, or auto-create account with ₹10,00,000 capital."""
    from services.google_auth_service import GoogleAuthService
    try:
        profile = GoogleAuthService.verify_id_token(payload.credential)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Google authentication failed: {exc}") from exc

    google_id = profile["google_id"]
    email = profile["email"]

    # 1. Match by google_id
    user = UserRepository.get_user_by_google_id(google_id)

    # 2. Match by email if not found by google_id, and auto-link
    if not user and email:
        user = UserRepository.get_user_by_email(email)
        if user:
            user = UserRepository.link_google_account(
                user_id=user["id"],
                google_id=google_id,
                email=email,
                avatar_url=profile.get("avatar_url"),
            )

    # 3. Create new user if not found
    if not user:
        user = UserRepository.create_google_user(
            google_id=google_id,
            email=email,
            display_name=profile.get("display_name") or "Google Trader",
            avatar_url=profile.get("avatar_url"),
        )

    token = UserRepository.create_session(user["id"])
    return {
        "success": True,
        "token": token,
        "user": user,
        "message": f"Welcome, {user.get('display_name') or user.get('username')}! Google account connected.",
    }


@router.post("/google/link", response_model=dict[str, Any])
def google_link_endpoint(
    payload: GoogleAuthRequest, current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Link Google account to currently authenticated profile."""
    if not current_user or current_user.get("id", 0) == 0:
        raise HTTPException(status_code=401, detail="Authentication required to link account")

    from services.google_auth_service import GoogleAuthService
    try:
        profile = GoogleAuthService.verify_id_token(payload.credential)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        updated_user = UserRepository.link_google_account(
            user_id=current_user["id"],
            google_id=profile["google_id"],
            email=profile["email"],
            avatar_url=profile.get("avatar_url"),
        )
        return {
            "success": True,
            "user": updated_user,
            "message": f"Successfully linked Google account ({profile['email']}) to @{current_user.get('username')}.",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/google/unlink", response_model=dict[str, Any])
def google_unlink_endpoint(
    current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Unlink Google account from currently authenticated profile."""
    if not current_user or current_user.get("id", 0) == 0:
        raise HTTPException(status_code=401, detail="Authentication required to unlink account")

    updated_user = UserRepository.unlink_google_account(current_user["id"])
    return {
        "success": True,
        "user": updated_user,
        "message": "Google account unlinked successfully.",
    }

