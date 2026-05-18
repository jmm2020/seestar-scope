"""Stripe webhook handler — FastAPI router.

Registers at /billing/webhook.
Validates Stripe-Signature header, deduplicates by event ID via Supabase
stripe_event_log table, then dispatches per-event handlers.

SQL migration (run once in Supabase SQL editor):
    CREATE TABLE IF NOT EXISTS public.stripe_event_log (
        event_id   TEXT PRIMARY KEY,
        type       TEXT NOT NULL,
        processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

NOTE: Do NOT create indexes on stripe_event_log beyond the PK — the table
will remain small (one row per webhook event) and a PK index is sufficient.
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

try:
    import stripe as _stripe_module
    _STRIPE_AVAILABLE = True
except ImportError:
    _STRIPE_AVAILABLE = False
    _stripe_module = None  # type: ignore[assignment]

try:
    from supabase import Client as SupabaseClient
    from supabase import create_client
    _SUPABASE_AVAILABLE = True
except ImportError:
    _SUPABASE_AVAILABLE = False
    SupabaseClient = None  # type: ignore[assignment,misc]
    create_client = None  # type: ignore[assignment]


_supabase: Optional["SupabaseClient"] = None


def _get_supabase() -> Optional["SupabaseClient"]:
    global _supabase
    if _supabase is not None:
        return _supabase
    if not _SUPABASE_AVAILABLE:
        logger.warning("supabase package not installed")
        return None
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        logger.warning(
            "webhook_handler: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set"
        )
        return None
    try:
        _supabase = create_client(url, key)
    except Exception as e:
        logger.error("Failed to create Supabase client: %s", e, exc_info=True)
        return None
    return _supabase


def _event_already_processed(event_id: str) -> bool:
    """Return True if event_id is already in stripe_event_log."""
    sb = _get_supabase()
    if sb is None:
        return False
    try:
        result = (
            sb.table("stripe_event_log")
            .select("event_id")
            .eq("event_id", event_id)
            .limit(1)
            .execute()
        )
        return len(result.data) > 0
    except Exception as e:
        logger.warning("Could not check stripe_event_log: %s", e)
        return False


def _log_event(event_id: str, event_type: str) -> None:
    """Insert event into stripe_event_log. Silently ignores errors."""
    sb = _get_supabase()
    if sb is None:
        return
    try:
        sb.table("stripe_event_log").insert(
            {"event_id": event_id, "type": event_type}
        ).execute()
    except Exception as e:
        logger.warning("Could not insert into stripe_event_log: %s", e)


def _handle_checkout_completed(session_obj: dict) -> None:
    """Bind Stripe customer_id → Supabase user_id on successful checkout."""
    customer_id = session_obj.get("customer")
    user_id = session_obj.get("client_reference_id")
    if not customer_id or not user_id:
        logger.warning(
            "checkout.session.completed missing customer or client_reference_id: %s",
            session_obj.get("id"),
        )
        return
    sb = _get_supabase()
    if sb is None:
        return
    try:
        sb.auth.admin.update_user_by_id(
            user_id,
            {"user_metadata": {"stripe_customer_id": customer_id}},
        )
        logger.info("Bound customer %s → user %s", customer_id, user_id)
    except Exception as e:
        logger.error("Failed to bind customer_id to user_id: %s", e, exc_info=True)


@router.post("/webhook", status_code=204)
async def stripe_webhook(request: Request):
    """Receive and process Stripe webhook events.

    Validates Stripe-Signature, deduplicates by event ID, then dispatches
    per-event handlers. Returns 204 on success (including deduped events).
    """
    if not _STRIPE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Stripe not available")

    body = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    try:
        event = _stripe_module.Webhook.construct_event(body, sig_header, webhook_secret)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except _stripe_module.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_id = event["id"]
    event_type = event["type"]

    if _event_already_processed(event_id):
        logger.debug("Skipping duplicate event %s", event_id)
        return

    _log_event(event_id, event_type)

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(event["data"]["object"])
    elif event_type == "invoice.payment_failed":
        invoice_id = event["data"]["object"].get("id")
        logger.warning("Payment failed for invoice %s", invoice_id)
    else:
        logger.debug("Unhandled event type: %s", event_type)
