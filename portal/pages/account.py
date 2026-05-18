"""Account page — login / signup / account info / logout.

Renders one of three states:
  1. OAuth callback (URL has ?code=) — exchange code for session.
  2. Authenticated — show account info + logout.
  3. Unauthenticated — show login/signup form + OAuth buttons.
"""

import logging
import os
from typing import Optional

import streamlit as st

from auth import session as auth_session
from auth.provider import AuthProvider
from auth.providers_config import get_oauth_providers

logger = logging.getLogger(__name__)

_PORTAL_URL = os.environ.get("PORTAL_URL", "http://localhost:8502")

_provider = AuthProvider()


def render_account() -> None:
    st.title("\U0001f464 Account")

    # 1. OAuth callback detection
    code = st.query_params.get("code")
    if code and not auth_session.is_authenticated():
        with st.spinner("Completing sign-in..."):
            sess = _provider.exchange_code_for_session(code)
            if sess:
                auth_session.store_session(sess)
                st.query_params.clear()
                st.rerun()
            else:
                st.error("OAuth sign-in failed. Please try again.")
        return

    # 2. Already authenticated
    if auth_session.is_authenticated():
        _render_account_panel()
        return

    # 3. Unauthenticated
    _render_auth_forms()


def _build_oauth_url(provider_name: str) -> Optional[str]:
    callback = f"{_PORTAL_URL}/"
    return _provider.sign_in_oauth(provider_name, redirect_to=callback)


def _switch_auth_view(view: str) -> None:
    st.session_state["auth_view"] = view
    st.rerun()


def _render_auth_forms() -> None:
    view = st.session_state.get("auth_view", "login")

    if view == "reset":
        _render_reset_form()
    elif view == "signup":
        _render_signup_form()
    else:
        _render_login_form()

    st.divider()
    _render_oauth_buttons()


def _render_login_form() -> None:
    st.subheader("Log In")
    with st.form("auth_login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log In", type="primary")
        if submitted:
            sess = _provider.sign_in_email(email, password)
            if sess:
                auth_session.store_session(sess)
                st.rerun()
            else:
                st.error("Invalid credentials. Please try again.")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Don't have an account? Sign up"):
            _switch_auth_view("signup")
    with col_b:
        if st.button("Forgot password?"):
            _switch_auth_view("reset")


def _render_signup_form() -> None:
    st.subheader("Sign Up")
    with st.form("auth_signup"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign Up", type="primary")
        if submitted:
            sess = _provider.sign_up_email(email, password)
            if sess:
                auth_session.store_session(sess)
                st.rerun()
            else:
                st.info("Check your inbox to confirm your email, then log in.")

    if st.button("Already have an account? Log in"):
        _switch_auth_view("login")


def _render_reset_form() -> None:
    st.subheader("Reset Password")
    with st.form("auth_reset"):
        email = st.text_input("Email")
        submitted = st.form_submit_button("Send Reset Email", type="primary")
        if submitted:
            ok = _provider.reset_password_email(email)
            if ok:
                st.success("Check your inbox for a password reset link.")
            else:
                st.error("Could not send reset email. Please try again later.")

    if st.button("Back to login"):
        _switch_auth_view("login")


def _render_oauth_buttons() -> None:
    providers = get_oauth_providers()
    if not providers:
        return
    st.caption("Or continue with:")
    for p in providers:
        url = _build_oauth_url(p.name)
        if not url:
            logger.warning("OAuth URL unavailable for provider %s — button suppressed", p.name)
            continue
        label = f"{p.icon} {p.label}".strip()
        st.link_button(label, url, use_container_width=True)


def _render_account_panel() -> None:
    email = auth_session.current_user_email() or "(unknown)"
    created_at = auth_session.current_user_created_at() or "(unknown)"
    st.info(f"**Signed in as:** {email}\n\n**Member since:** {created_at}")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Log Out", type="primary"):
            sess = auth_session.get_session()
            if sess:
                access_token = getattr(sess, "access_token", "")
                refresh_token = getattr(sess, "refresh_token", "")
                if access_token:
                    _provider.sign_out(access_token, refresh_token)
            auth_session.clear_session()
            st.rerun()
    with col_b:
        st.button("Manage Billing", disabled=True, help="Coming soon")
