"""Tests for billing/webhook_handler.py."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from billing.webhook_handler import router  # noqa: E402

_app = FastAPI()
_app.include_router(router)
client = TestClient(_app)


def _make_event(event_type="checkout.session.completed", event_id="evt_test_001"):
    return {
        "id": event_id,
        "type": event_type,
        "data": {
            "object": {
                "id": "cs_test_123",
                "customer": "cus_test_123",
                "client_reference_id": "uid-user-123",
            }
        },
    }


def test_valid_webhook_returns_204():
    event = _make_event()
    mock_stripe = MagicMock()
    mock_stripe.Webhook.construct_event.return_value = event
    with patch("billing.webhook_handler._stripe_module", mock_stripe), \
         patch("billing.webhook_handler._STRIPE_AVAILABLE", True), \
         patch("billing.webhook_handler._event_already_processed", return_value=False), \
         patch("billing.webhook_handler._log_event"), \
         patch("billing.webhook_handler._handle_checkout_completed"):
        resp = client.post(
            "/billing/webhook",
            content=b'{"id":"evt_test_001"}',
            headers={"stripe-signature": "t=123,v1=abc"},
        )
    assert resp.status_code == 204


def test_invalid_signature_returns_400():
    import stripe as _stripe_real
    mock_stripe = MagicMock()
    mock_stripe.Webhook.construct_event.side_effect = (
        _stripe_real.error.SignatureVerificationError("bad sig", "t=123,v1=bad")
    )
    mock_stripe.error.SignatureVerificationError = (
        _stripe_real.error.SignatureVerificationError
    )
    with patch("billing.webhook_handler._stripe_module", mock_stripe), \
         patch("billing.webhook_handler._STRIPE_AVAILABLE", True):
        resp = client.post(
            "/billing/webhook",
            content=b"{}",
            headers={"stripe-signature": "t=123,v1=bad"},
        )
    assert resp.status_code == 400


def test_duplicate_event_returns_204_without_processing():
    event = _make_event(event_id="evt_dupe_001")
    mock_stripe = MagicMock()
    mock_stripe.Webhook.construct_event.return_value = event
    with patch("billing.webhook_handler._stripe_module", mock_stripe), \
         patch("billing.webhook_handler._STRIPE_AVAILABLE", True), \
         patch("billing.webhook_handler._event_already_processed", return_value=True), \
         patch("billing.webhook_handler._handle_checkout_completed") as mock_handle:
        resp = client.post(
            "/billing/webhook",
            content=b'{"id":"evt_dupe_001"}',
            headers={"stripe-signature": "t=123,v1=abc"},
        )
    assert resp.status_code == 204
    mock_handle.assert_not_called()


def test_payment_failed_event_logs_warning(caplog):
    import logging
    event = _make_event(event_type="invoice.payment_failed")
    event["data"]["object"] = {"id": "in_fail_001"}
    mock_stripe = MagicMock()
    mock_stripe.Webhook.construct_event.return_value = event
    with patch("billing.webhook_handler._stripe_module", mock_stripe), \
         patch("billing.webhook_handler._STRIPE_AVAILABLE", True), \
         patch("billing.webhook_handler._event_already_processed", return_value=False), \
         patch("billing.webhook_handler._log_event"), \
         caplog.at_level(logging.WARNING, logger="billing.webhook_handler"):
        resp = client.post(
            "/billing/webhook",
            content=b'{}',
            headers={"stripe-signature": "t=123,v1=abc"},
        )
    assert resp.status_code == 204
    assert "in_fail_001" in caplog.text
