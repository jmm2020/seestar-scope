"""Billing product constants and subscription helpers."""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

WATCH_PRICE_ID: Optional[str] = os.environ.get("STRIPE_WATCH_PRICE_ID")
CONTROL_PRICE_ID: Optional[str] = os.environ.get("STRIPE_CONTROL_PRICE_ID")

WATCH_TRIAL_DAYS = 7


def is_first_watch_signup(user_id: str, supabase_client=None) -> bool:
    """Return True if user_id has never had a Watch subscription.

    Queries the stripe.subscriptions table written by the Supabase Stripe
    Sync Engine. Returns True (allow trial) if Supabase is unreachable or the
    table doesn't exist — safe fallback that errs toward user-friendly.
    """
    if supabase_client is None:
        return True
    try:
        result = (
            supabase_client.schema("stripe")
            .from_("subscriptions")
            .select("id")
            .eq("metadata->>user_id", user_id)
            .limit(1)
            .execute()
        )
        return len(result.data) == 0
    except Exception as e:
        logger.warning(
            "is_first_watch_signup: could not query stripe.subscriptions — "
            "defaulting to True: %s", e
        )
        return True
