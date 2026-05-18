"""Tests for auth.session — st.session_state binding."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Stub streamlit BEFORE importing session module
_st_mock = MagicMock()
_session_state_dict: dict = {}
_st_mock.session_state = _session_state_dict
sys.modules["streamlit"] = _st_mock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest  # noqa: E402

import auth.session as auth_session  # noqa: E402


def _make_session(email="user@test.com", user_id="uid-1", expires_at=None):
    sess = MagicMock()
    sess.user.id = user_id
    sess.user.email = email
    sess.access_token = "tok"
    sess.expires_at = expires_at
    return sess


@pytest.fixture(autouse=True)
def clear_state():
    _session_state_dict.clear()
    yield
    _session_state_dict.clear()


def test_store_and_retrieve_session():
    sess = _make_session()
    auth_session.store_session(sess)
    assert auth_session.get_session() is sess


def test_clear_session():
    auth_session.store_session(_make_session())
    auth_session.clear_session()
    assert auth_session.get_session() is None


def test_is_authenticated_false_when_no_session():
    assert not auth_session.is_authenticated()


def test_is_authenticated_true_when_session_present():
    auth_session.store_session(_make_session())
    assert auth_session.is_authenticated()


def test_is_authenticated_false_when_expired():
    sess = _make_session(expires_at=1)  # past Unix timestamp
    auth_session.store_session(sess)
    assert not auth_session.is_authenticated()


def test_expired_session_is_cleared_from_state():
    sess = _make_session(expires_at=1)
    auth_session.store_session(sess)
    auth_session.is_authenticated()
    assert "auth_session" not in _session_state_dict


def test_current_user_id_extracts_correctly():
    auth_session.store_session(_make_session(user_id="my-uuid"))
    assert auth_session.current_user_id() == "my-uuid"


def test_current_user_email_extracts_correctly():
    auth_session.store_session(_make_session(email="hello@test.com"))
    assert auth_session.current_user_email() == "hello@test.com"


def test_current_user_id_returns_none_when_unauthed():
    assert auth_session.current_user_id() is None
