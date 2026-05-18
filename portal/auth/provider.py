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
        if not self._url or not self._anon_key:
            logger.warning(
                "AuthProvider: SUPABASE_URL or SUPABASE_ANON_KEY not set — "
                "all auth operations will fail. Set these in your .env file."
            )

    def _get_client(self) -> Optional["Client"]:
        # Check injected client first so tests can pass a MagicMock without supabase installed.
        if self._client is not None:
            return self._client
        if not _SUPABASE_AVAILABLE:
            logger.warning("supabase package not installed")
            return None
        if not self._url or not self._anon_key:
            logger.warning("SUPABASE_URL or SUPABASE_ANON_KEY not set")
            return None
        try:
            self._client = create_client(self._url, self._anon_key)
        except Exception as e:
            logger.error("Failed to create Supabase client: %s", e, exc_info=True)
            return None
        return self._client

    def sign_up_email(self, email: str, password: str) -> Optional["Session"]:
        client = self._get_client()
        if client is None:
            return None
        try:
            resp = client.auth.sign_up({"email": email, "password": password})
            return resp.session
        except Exception as e:
            logger.error("sign_up_email failed: %s", e, exc_info=True)
            return None

    def sign_in_email(self, email: str, password: str) -> Optional["Session"]:
        client = self._get_client()
        if client is None:
            return None
        try:
            resp = client.auth.sign_in_with_password({"email": email, "password": password})
            return resp.session
        except Exception as e:
            logger.error("sign_in_email failed: %s", e, exc_info=True)
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
            logger.error("sign_in_oauth(%s) failed: %s", provider_name, e, exc_info=True)
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
            logger.error("exchange_code_for_session failed: %s", e, exc_info=True)
            return None

    def sign_out(self, access_token: str, refresh_token: str = "") -> bool:
        """Sign out via the user-level API (anon key sufficient).

        Sets the session on the client so the anon-key client can invalidate
        the token server-side.  Caller should always clear local session state
        regardless of return value.
        """
        client = self._get_client()
        if client is None:
            return False
        try:
            client.auth.set_session(access_token, refresh_token)
            client.auth.sign_out()
            return True
        except Exception as e:
            logger.error("sign_out failed: %s", e, exc_info=True)
            return False

    def reset_password_email(self, email: str) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            client.auth.reset_password_email(email)
            return True
        except Exception as e:
            logger.error("reset_password_email failed: %s", e, exc_info=True)
            return False
