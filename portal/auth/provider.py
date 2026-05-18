"""Supabase Auth client wrapper.

Wraps the supabase-py SDK into a clean method surface.
Network / auth failures are caught and logged — callers receive None on failure.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from supabase import Client, create_client
    from gotrue.types import Session, User

    _SUPABASE_AVAILABLE = True
except ImportError:
    _SUPABASE_AVAILABLE = False
    Client = None  # type: ignore[assignment,misc]
    Session = None  # type: ignore[assignment,misc]
    User = None  # type: ignore[assignment,misc]
    create_client = None  # type: ignore[assignment]


class AuthProvider:
    def __init__(
        self,
        supabase_url: Optional[str] = None,
        anon_key: Optional[str] = None,
        jwt_secret: Optional[str] = None,
    ):
        self._url = supabase_url or os.environ.get("SUPABASE_URL", "")
        self._anon_key = anon_key or os.environ.get("SUPABASE_ANON_KEY", "")
        self._jwt_secret = jwt_secret or os.environ.get("SUPABASE_JWT_SECRET", "")
        self._client: Optional["Client"] = None

    def _get_client(self) -> Optional["Client"]:
        if self._client is not None:
            return self._client
        if not _SUPABASE_AVAILABLE:
            logger.warning("supabase package not installed")
            return None
        if not self._url or not self._anon_key:
            logger.warning("SUPABASE_URL or SUPABASE_ANON_KEY not set")
            return None
        self._client = create_client(self._url, self._anon_key)
        return self._client

    def sign_up_email(self, email: str, password: str) -> Optional["Session"]:
        client = self._get_client()
        if client is None:
            return None
        try:
            resp = client.auth.sign_up({"email": email, "password": password})
            return resp.session
        except Exception as e:
            logger.warning(f"sign_up_email failed: {e}")
            return None

    def sign_in_email(self, email: str, password: str) -> Optional["Session"]:
        client = self._get_client()
        if client is None:
            return None
        try:
            resp = client.auth.sign_in_with_password({"email": email, "password": password})
            return resp.session
        except Exception as e:
            logger.warning(f"sign_in_email failed: {e}")
            return None

    def sign_in_oauth(self, provider_name: str, redirect_to: str) -> Optional[str]:
        """Return the OAuth redirect URL, or None on failure."""
        client = self._get_client()
        if client is None:
            return None
        try:
            resp = client.auth.sign_in_with_oauth(
                {
                    "provider": provider_name,
                    "options": {
                        "redirect_to": redirect_to,
                        "skip_browser_redirect": True,
                    },
                }
            )
            return resp.url
        except Exception as e:
            logger.warning(f"sign_in_oauth({provider_name}) failed: {e}")
            return None

    def exchange_code_for_session(self, auth_code: str) -> Optional["Session"]:
        """Exchange OAuth auth code (PKCE) for a Session."""
        client = self._get_client()
        if client is None:
            return None
        try:
            resp = client.auth.exchange_code_for_session({"auth_code": auth_code})
            return resp.session
        except Exception as e:
            logger.warning(f"exchange_code_for_session failed: {e}")
            return None

    def sign_out(self, access_token: str) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            client.auth.admin.sign_out(access_token)
            return True
        except Exception as e:
            logger.warning(f"sign_out failed: {e}")
            return False

    def reset_password_email(self, email: str) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            client.auth.reset_password_email(email)
            return True
        except Exception as e:
            logger.warning(f"reset_password_email failed: {e}")
            return False
