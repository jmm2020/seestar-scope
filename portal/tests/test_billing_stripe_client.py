"""Tests for StripeClient — mocked Stripe SDK, no live Stripe required."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest  # noqa: E402

from billing.stripe_client import StripeClient  # noqa: E402


@pytest.fixture
def client():
    return StripeClient(secret_key="sk_test_fake")


def test_get_or_create_customer_returns_existing(client):
    mock_stripe = MagicMock()
    mock_stripe.Customer.list.return_value.data = [MagicMock(id="cus_existing")]
    with patch("billing.stripe_client._stripe", mock_stripe), \
         patch("billing.stripe_client._STRIPE_AVAILABLE", True):
        result = client.get_or_create_customer("uid-1", "user@test.com")
    assert result == "cus_existing"


def test_get_or_create_customer_creates_new_when_none_exist(client):
    mock_stripe = MagicMock()
    mock_stripe.Customer.list.return_value.data = []
    mock_stripe.Customer.create.return_value.id = "cus_new"
    with patch("billing.stripe_client._stripe", mock_stripe), \
         patch("billing.stripe_client._STRIPE_AVAILABLE", True):
        result = client.get_or_create_customer("uid-1", "user@test.com")
    assert result == "cus_new"
    mock_stripe.Customer.create.assert_called_once()


def test_create_checkout_session_with_trial(client):
    mock_stripe = MagicMock()
    mock_stripe.checkout.Session.create.return_value.url = (
        "https://checkout.stripe.com/pay/cs_test_abc"
    )
    with patch("billing.stripe_client._stripe", mock_stripe), \
         patch("billing.stripe_client._STRIPE_AVAILABLE", True):
        url = client.create_checkout_session(
            user_id="uid-1",
            price_id="price_watch",
            customer_id="cus_123",
            success_url="https://app/success",
            cancel_url="https://app/cancel",
            trial_days=7,
        )
    assert url == "https://checkout.stripe.com/pay/cs_test_abc"
    call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
    assert call_kwargs["subscription_data"]["trial_period_days"] == 7
    assert call_kwargs["client_reference_id"] == "uid-1"


def test_create_checkout_session_no_trial(client):
    mock_stripe = MagicMock()
    mock_stripe.checkout.Session.create.return_value.url = (
        "https://checkout.stripe.com/pay/cs_test_abc"
    )
    with patch("billing.stripe_client._stripe", mock_stripe), \
         patch("billing.stripe_client._STRIPE_AVAILABLE", True):
        client.create_checkout_session(
            user_id="uid-1",
            price_id="price_watch",
            customer_id="cus_123",
            success_url="https://app/success",
            cancel_url="https://app/cancel",
            trial_days=None,
        )
    call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
    assert "subscription_data" not in call_kwargs


def test_create_checkout_session_returns_none_on_exception(client):
    mock_stripe = MagicMock()
    mock_stripe.checkout.Session.create.side_effect = Exception("api error")
    with patch("billing.stripe_client._stripe", mock_stripe), \
         patch("billing.stripe_client._STRIPE_AVAILABLE", True):
        result = client.create_checkout_session(
            "uid-1", "price_watch", "cus_123", "u", "u"
        )
    assert result is None


def test_create_portal_session_returns_url(client):
    mock_stripe = MagicMock()
    mock_stripe.billing_portal.Session.create.return_value.url = (
        "https://billing.stripe.com/p/session_abc"
    )
    with patch("billing.stripe_client._stripe", mock_stripe), \
         patch("billing.stripe_client._STRIPE_AVAILABLE", True):
        url = client.create_customer_portal_session("cus_123", "https://app/account")
    assert url == "https://billing.stripe.com/p/session_abc"


def test_create_portal_session_returns_none_on_exception(client):
    mock_stripe = MagicMock()
    mock_stripe.billing_portal.Session.create.side_effect = Exception("portal error")
    with patch("billing.stripe_client._stripe", mock_stripe), \
         patch("billing.stripe_client._STRIPE_AVAILABLE", True):
        result = client.create_customer_portal_session("cus_123", "https://app/account")
    assert result is None


def test_returns_none_when_stripe_unavailable():
    c = StripeClient(secret_key="sk_test_fake")
    with patch("billing.stripe_client._STRIPE_AVAILABLE", False):
        assert c.get_or_create_customer("uid-1", "user@test.com") is None
