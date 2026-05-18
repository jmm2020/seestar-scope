"""Checkout page — Subscribe to Watch tier / Manage billing.

Renders based on auth + Stripe config state:
  - Not authenticated → info message
  - Authenticated, no Stripe config → show warning
  - Authenticated, has Stripe config → Subscribe / Manage Billing buttons
"""

import logging
import os
from typing import Optional

import streamlit as st

from auth import session as auth_session
from billing.products import WATCH_PRICE_ID, WATCH_TRIAL_DAYS, is_first_watch_signup
from billing.stripe_client import StripeClient

logger = logging.getLogger(__name__)

_PORTAL_URL = os.environ.get("PORTAL_URL", "http://localhost:8502")

_stripe_client: Optional[StripeClient] = None


def _get_stripe_client() -> StripeClient:
    global _stripe_client
    if _stripe_client is None:
        _stripe_client = StripeClient()
    return _stripe_client


def render_checkout() -> None:
    st.title("\U0001f4b3 Billing")

    if not auth_session.is_authenticated():
        st.info("Please sign in to manage your subscription.")
        return

    user_id = auth_session.current_user_id()
    email = auth_session.current_user_email() or ""

    if not WATCH_PRICE_ID:
        st.warning("Billing is not configured (STRIPE_WATCH_PRICE_ID not set).")
        return

    st.subheader("Watch Tier — $9.99 / month")
    st.caption("Live view, MJPEG stream, telescope status")

    if st.button("Subscribe to Watch", type="primary"):
        _start_checkout(user_id, email)

    st.divider()

    if st.button("Manage Billing"):
        _open_portal(user_id, email)


def _start_checkout(user_id: str, email: str) -> None:
    customer_id = _get_stripe_client().get_or_create_customer(user_id, email)
    if not customer_id:
        st.error("Could not create billing customer. Please try again.")
        return

    # TODO(#62): pass supabase_client once entitlement module is implemented;
    # until then defaults to True (all users get trial).
    first_signup = is_first_watch_signup(user_id)
    trial_days = WATCH_TRIAL_DAYS if first_signup else None

    success_url = f"{_PORTAL_URL}/?billing=success"
    cancel_url = f"{_PORTAL_URL}/Account"

    url = _get_stripe_client().create_checkout_session(
        user_id=user_id,
        price_id=WATCH_PRICE_ID,
        customer_id=customer_id,
        success_url=success_url,
        cancel_url=cancel_url,
        trial_days=trial_days,
    )
    if url:
        st.link_button("Proceed to Checkout", url, type="primary")
    else:
        st.error("Could not create checkout session. Please try again.")


def _open_portal(user_id: str, email: str) -> None:
    customer_id = _get_stripe_client().get_or_create_customer(user_id, email)
    if not customer_id:
        st.error("No billing account found.")
        return

    return_url = f"{_PORTAL_URL}/Account"
    url = _get_stripe_client().create_customer_portal_session(customer_id, return_url)
    if url:
        st.link_button("Open Billing Portal", url, type="primary")
    else:
        st.error("Could not open billing portal. Please try again.")


render_checkout()
