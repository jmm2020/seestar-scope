"""Streamlit session-state binding for Supabase JWT.

Functions that read/write st.session_state["auth_session"].
No network calls — pure state manipulation.
"""

import logging
import time
from typing import Optional

import streamlit as st

logger = logging.getLogger(__name__)

_SESSION_KEY = "auth_session"


def store_session(session) -> None:
    """Store a gotrue Session in st.session_state."""
    st.session_state[_SESSION_KEY] = session


def clear_session() -> None:
    """Remove auth session from st.session_state."""
    st.session_state.pop(_SESSION_KEY, None)


def get_session():
    """Return the stored Session, or None if not present / expired."""
    session = st.session_state.get(_SESSION_KEY)
    if session is None:
        return None
    expires_at = getattr(session, "expires_at", None)
    if expires_at is not None and time.time() > expires_at:
        clear_session()
        return None
    return session


def is_authenticated() -> bool:
    return get_session() is not None


def current_user_id() -> Optional[str]:
    session = get_session()
    if session is None:
        return None
    return getattr(getattr(session, "user", None), "id", None)


def current_user_email() -> Optional[str]:
    session = get_session()
    if session is None:
        return None
    return getattr(getattr(session, "user", None), "email", None)


def current_user_created_at() -> Optional[str]:
    session = get_session()
    if session is None:
        return None
    return getattr(getattr(session, "user", None), "created_at", None)
