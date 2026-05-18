"""Tests for billing/products.py."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from billing.products import WATCH_TRIAL_DAYS, is_first_watch_signup  # noqa: E402


def test_watch_trial_days_is_seven():
    assert WATCH_TRIAL_DAYS == 7


def test_is_first_signup_returns_true_when_no_subscriptions():
    mock_sb = MagicMock()
    mock_sb.schema.return_value.from_.return_value \
        .select.return_value.eq.return_value \
        .limit.return_value.execute.return_value.data = []
    assert is_first_watch_signup("uid-1", supabase_client=mock_sb) is True


def test_is_first_signup_returns_false_when_subscription_exists():
    mock_sb = MagicMock()
    mock_sb.schema.return_value.from_.return_value \
        .select.return_value.eq.return_value \
        .limit.return_value.execute.return_value.data = [{"id": "sub_abc"}]
    assert is_first_watch_signup("uid-1", supabase_client=mock_sb) is False


def test_is_first_signup_returns_true_when_supabase_raises():
    mock_sb = MagicMock()
    mock_sb.schema.side_effect = Exception("connection error")
    assert is_first_watch_signup("uid-1", supabase_client=mock_sb) is True


def test_is_first_signup_returns_true_when_no_client():
    assert is_first_watch_signup("uid-1", supabase_client=None) is True
