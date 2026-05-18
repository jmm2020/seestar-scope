"""Tests for pages/account.py helper functions."""

import sys
import unittest.mock as um
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# Stub streamlit with a real dict for session_state so that auth.session works
# correctly in the full test suite (test_auth_session.py depends on this).
if "streamlit" not in sys.modules:
    _st_stub = MagicMock()
    _st_stub.session_state = {}
    sys.modules["streamlit"] = _st_stub

def _make_col_mocks():
    """Return a (col_a, col_b) pair of context-manager-compatible mocks."""
    col_a = MagicMock()
    col_a.__enter__ = MagicMock(return_value=col_a)
    col_a.__exit__ = MagicMock(return_value=False)
    col_b = MagicMock()
    col_b.__enter__ = MagicMock(return_value=col_b)
    col_b.__exit__ = MagicMock(return_value=False)
    return col_a, col_b


def _load_account_module():
    import pages.account as _mod
    return _mod


@pytest.fixture(scope="module")
def account_module():
    return _load_account_module()


@pytest.fixture()
def mock_provider(account_module, monkeypatch):
    p = MagicMock()
    monkeypatch.setattr(account_module, "_provider", p)
    return p


@pytest.fixture()
def mock_session_mod(account_module, monkeypatch):
    s = MagicMock()
    monkeypatch.setattr(account_module, "auth_session", s)
    return s


def test_build_oauth_url_returns_provider_url(account_module, mock_provider):
    mock_provider.sign_in_oauth.return_value = "https://accounts.google.com/..."
    url = account_module._build_oauth_url("google")
    assert url == "https://accounts.google.com/..."
    mock_provider.sign_in_oauth.assert_called_once()


def test_build_oauth_url_returns_none_when_provider_fails(account_module, mock_provider):
    mock_provider.sign_in_oauth.return_value = None
    url = account_module._build_oauth_url("google")
    assert url is None


def test_build_oauth_url_callback_does_not_include_page_param(account_module, mock_provider):
    mock_provider.sign_in_oauth.return_value = "https://accounts.google.com/..."
    account_module._build_oauth_url("google")
    _, kwargs = mock_provider.sign_in_oauth.call_args
    assert "page=" not in kwargs["redirect_to"]


def test_render_account_skips_code_exchange_when_already_authed(
    account_module, mock_provider, mock_session_mod
):
    """?code= present but already authenticated — exchange must NOT be called."""
    st_mock = MagicMock()
    st_mock.query_params.get.return_value = "auth-code-xyz"
    mock_session_mod.is_authenticated.return_value = True
    # _render_account_panel unpacks st.columns(2) — must return a 2-tuple
    st_mock.columns.return_value = _make_col_mocks()

    with um.patch.object(account_module, "st", st_mock):
        account_module.render_account()

    mock_provider.exchange_code_for_session.assert_not_called()


def test_render_account_exchanges_code_when_not_authed(
    account_module, mock_provider, mock_session_mod
):
    st_mock = MagicMock()
    st_mock.query_params.get.return_value = "auth-code-xyz"
    mock_session_mod.is_authenticated.return_value = False
    fake_sess = MagicMock()
    mock_provider.exchange_code_for_session.return_value = fake_sess

    with um.patch.object(account_module, "st", st_mock):
        account_module.render_account()

    mock_provider.exchange_code_for_session.assert_called_once_with("auth-code-xyz")
    mock_session_mod.store_session.assert_called_once_with(fake_sess)


def test_render_account_panel_logout_calls_sign_out_and_clears(
    account_module, mock_provider, mock_session_mod
):
    st_mock = MagicMock()
    col_a_mock, col_b_mock = _make_col_mocks()
    col_a_mock.button.return_value = True
    st_mock.columns.return_value = (col_a_mock, col_b_mock)

    fake_sess = MagicMock()
    fake_sess.access_token = "tok123"
    fake_sess.refresh_token = "ref456"
    mock_session_mod.get_session.return_value = fake_sess
    mock_session_mod.current_user_email.return_value = "user@test.com"
    mock_session_mod.current_user_created_at.return_value = "2024-01-01"

    with um.patch.object(account_module, "st", st_mock):
        account_module._render_account_panel()

    mock_provider.sign_out.assert_called_once_with("tok123", "ref456")
    mock_session_mod.clear_session.assert_called_once()


def test_render_oauth_buttons_suppresses_button_when_url_none(
    account_module, mock_provider, monkeypatch
):
    fake_providers = [MagicMock(name="google", icon="G", label="Google")]
    monkeypatch.setattr(account_module, "get_oauth_providers", lambda: fake_providers)
    mock_provider.sign_in_oauth.return_value = None

    st_mock = MagicMock()
    with um.patch.object(account_module, "st", st_mock):
        account_module._render_oauth_buttons()

    st_mock.link_button.assert_not_called()
