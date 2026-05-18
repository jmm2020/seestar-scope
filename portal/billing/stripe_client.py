"""Stripe SDK wrapper.

Exposes three public methods:
  create_checkout_session(user_id, price_id, customer_id, trial_days=None) -> str | None
  create_customer_portal_session(customer_id, return_url) -> str | None
  get_or_create_customer(user_id, email) -> str | None

All network/auth failures are caught and logged; callers receive None on failure.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import stripe as _stripe
    _STRIPE_AVAILABLE = True
except ImportError:
    _STRIPE_AVAILABLE = False
    _stripe = None  # type: ignore[assignment]


class StripeClient:
    def __init__(
        self,
        secret_key: Optional[str] = None,
    ):
        self._secret_key = secret_key or os.environ.get("STRIPE_SECRET_KEY", "")
        if not self._secret_key:
            logger.warning(
                "StripeClient: STRIPE_SECRET_KEY not set — all Stripe operations will fail."
            )

    def _get_stripe(self):
        """Return the stripe module configured with our key, or None if unavailable."""
        if not _STRIPE_AVAILABLE:
            logger.warning("stripe package not installed")
            return None
        if not self._secret_key:
            logger.warning("STRIPE_SECRET_KEY not set")
            return None
        _stripe.api_key = self._secret_key
        return _stripe

    def get_or_create_customer(self, user_id: str, email: str) -> Optional[str]:
        """Return existing Stripe customer ID for email, creating one if absent."""
        s = self._get_stripe()
        if s is None:
            return None
        try:
            existing = s.Customer.list(email=email, limit=1)
            if existing.data:
                return existing.data[0].id
            customer = s.Customer.create(
                email=email, metadata={"user_id": user_id}
            )
            return customer.id
        except Exception as e:
            logger.error("get_or_create_customer failed: %s", e, exc_info=True)
            return None

    def create_checkout_session(
        self,
        user_id: str,
        price_id: str,
        customer_id: str,
        success_url: str,
        cancel_url: str,
        trial_days: Optional[int] = None,
    ) -> Optional[str]:
        """Return a Stripe Checkout session URL, or None on failure."""
        s = self._get_stripe()
        if s is None:
            return None
        try:
            params: dict = {
                "mode": "subscription",
                "line_items": [{"price": price_id, "quantity": 1}],
                "customer": customer_id,
                "client_reference_id": user_id,
                "success_url": success_url,
                "cancel_url": cancel_url,
            }
            if trial_days is not None:
                params["subscription_data"] = {"trial_period_days": trial_days}
            session = s.checkout.Session.create(**params)
            return session.url
        except Exception as e:
            logger.error("create_checkout_session failed: %s", e, exc_info=True)
            return None

    def create_customer_portal_session(
        self,
        customer_id: str,
        return_url: str,
    ) -> Optional[str]:
        """Return a Stripe Customer Portal URL, or None on failure."""
        s = self._get_stripe()
        if s is None:
            return None
        try:
            session = s.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            return session.url
        except Exception as e:
            logger.error("create_customer_portal_session failed: %s", e, exc_info=True)
            return None
