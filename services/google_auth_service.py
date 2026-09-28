"""Google OAuth 2.0 ID Token verification service."""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from core.config import settings

logger = logging.getLogger(__name__)

GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
VALID_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class GoogleAuthService:
    """Verifies Google ID tokens and extracts verified user identity."""

    @classmethod
    def verify_id_token(cls, credential: str) -> dict[str, Any]:
        """Validate a Google ID token via Google's tokeninfo endpoint.
        
        Returns:
            dict containing:
                - google_id (str): Unique Google user ID (sub)
                - email (str): User's Google email address
                - display_name (str): Full name or email prefix
                - avatar_url (str): Profile picture URL
        
        Raises:
            ValueError: If token is invalid, expired, or audience doesn't match.
        """
        if not credential or not isinstance(credential, str):
            raise ValueError("Google credential token is missing or empty")

        clean_token = credential.strip()

        # Query Google's tokeninfo endpoint
        query_url = f"{GOOGLE_TOKENINFO_URL}?id_token={urllib.parse.quote(clean_token)}"
        try:
            req = urllib.request.Request(
                query_url,
                headers={"User-Agent": "StratLab-Terminal-Auth/1.0"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status != 200:
                    raise ValueError(f"Google token validation returned HTTP {resp.status}")
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_msg = "Invalid or expired Google token"
            try:
                err_body = json.loads(exc.read().decode("utf-8"))
                err_msg = err_body.get("error_description") or err_body.get("error") or err_msg
            except Exception:
                pass
            logger.warning(f"Google token verification failed: {err_msg}")
            raise ValueError(f"Google authentication failed: {err_msg}") from exc
        except Exception as exc:
            logger.error(f"Error reaching Google tokeninfo: {exc}")
            raise ValueError(f"Could not contact Google authentication server: {exc}") from exc

        # 1. Verify issuer
        iss = payload.get("iss", "")
        if iss not in VALID_ISSUERS:
            raise ValueError(f"Invalid Google token issuer: {iss}")

        # 2. Verify audience if GOOGLE_CLIENT_ID is configured
        expected_client_id = settings.GOOGLE_CLIENT_ID.strip()
        aud = payload.get("aud", "")
        if expected_client_id and aud != expected_client_id:
            raise ValueError("Google token client ID does not match configured application client ID")

        # 3. Verify sub (Google User ID)
        google_id = payload.get("sub")
        if not google_id:
            raise ValueError("Google token did not contain a valid user subject ID (sub)")

        # 4. Verify email
        email = payload.get("email", "").strip().lower()
        email_verified = payload.get("email_verified")
        if email_verified not in (True, "true", "True", 1):
            raise ValueError("Google email address is not verified")

        name = payload.get("name") or payload.get("given_name") or (email.split("@")[0] if email else "Google Trader")
        avatar_url = payload.get("picture", "")

        return {
            "google_id": str(google_id),
            "email": email,
            "display_name": name,
            "avatar_url": avatar_url,
        }
