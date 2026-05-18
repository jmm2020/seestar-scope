"""Tests for AuthProvider — mocked supabase client, no live Supabase required."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest  # noqa: E402

from auth.provider import AuthProvider  # noqa: E402


def _mock_session(email="test@example.com"):
    sess = MagicMock()
    sess.user.id = "uid-123"
    sess.user.email = email
    sess.access_token = "eyJfake"
    sess.expires_at = 9999999999
    return sess


@pytest.fixture
def provider():
    p = AuthProvider(
        supabase_url="https://x.supabase.co", anon_key="anon-key", jwt_secret="secret"
    )
    p._client = MagicMock()
    return p


def test_sign_in_email_returns_session_on_success(provider):
    provider._client.auth.sign_in_with_password.return_value.session = _mock_session()
    result = provider.sign_in_email("u@t.com", "pw")
    provider._client.auth.sign_in_with_password.assert_called_once_with(
        {"email": "u@t.com", "password": "pw"}
    )
    assert result is not None


def test_sign_in_email_returns_none_on_exception(provider):
    provider._client.auth.sign_in_with_password.side_effect = Exception("auth error")
    assert provider.sign_in_email("u@t.com", "pw") is None


def test_sign_up_email_returns_session_on_success(provider):
    provider._client.auth.sign_up.return_value.session = _mock_session()
    result = provider.sign_up_email("new@t.com", "pass1234")
    provider._client.auth.sign_up.assert_called_once_with(
        {"email": "new@t.com", "password": "pass1234"}
    )
    assert result is not None


def test_sign_up_email_returns_none_on_exception(provider):
    provider._client.auth.sign_up.side_effect = Exception("signup error")
    assert provider.sign_up_email("u@t.com", "pw") is None


def test_sign_in_oauth_returns_url(provider):
    provider._client.auth.sign_in_with_oauth.return_value.url = (
        "https://accounts.google.com/..."
    )
    url = provider.sign_in_oauth("google", redirect_to="http://localhost:8502/")
    assert url == "https://accounts.google.com/..."


def test_sign_in_oauth_returns_none_on_exception(provider):
    provider._client.auth.sign_in_with_oauth.side_effect = Exception("oauth error")
    assert provider.sign_in_oauth("google", redirect_to="http://x") is None


def test_exchange_code_returns_session(provider):
    provider._client.auth.exchange_code_for_session.return_value.session = _mock_session()
    result = provider.exchange_code_for_session("auth-code-123")
    provider._client.auth.exchange_code_for_session.assert_called_once_with(
        {"auth_code": "auth-code-123"}
    )
    assert result is not None


def test_exchange_code_returns_none_on_exception(provider):
    provider._client.auth.exchange_code_for_session.side_effect = Exception("bad code")
    assert provider.exchange_code_for_session("auth-code-123") is None


def test_sign_out_returns_true_on_success(provider):
    assert provider.sign_out("tok") is True


def test_sign_out_returns_false_on_exception(provider):
    provider._client.auth.admin.sign_out.side_effect = Exception("signout error")
    assert provider.sign_out("tok") is False


def test_reset_password_email_returns_true_on_success(provider):
    assert provider.reset_password_email("u@t.com") is True
    provider._client.auth.reset_password_email.assert_called_once_with("u@t.com")


def test_get_client_returns_none_when_url_missing(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    p = AuthProvider(supabase_url="", anon_key="")
    assert p._get_client() is None
