"""Tests for auth providers config — purely data-driven, no stubs required."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from auth.providers_config import (  # noqa: E402
    PROVIDERS,
    get_enabled_providers,
    get_oauth_providers,
)


def test_get_enabled_providers_returns_only_enabled():
    enabled = get_enabled_providers()
    assert all(p.enabled for p in enabled)


def test_v1_enabled_providers_are_email_and_google():
    enabled_names = [p.name for p in get_enabled_providers()]
    assert "email" in enabled_names
    assert "google" in enabled_names


def test_get_oauth_providers_excludes_email():
    oauth = get_oauth_providers()
    assert all(p.name != "email" for p in oauth)


def test_google_is_oauth_provider():
    oauth_names = [p.name for p in get_oauth_providers()]
    assert "google" in oauth_names


def test_disabled_providers_not_in_enabled_set():
    enabled_names = {p.name for p in get_enabled_providers()}
    disabled_names = {p.name for p in PROVIDERS if not p.enabled}
    assert enabled_names.isdisjoint(disabled_names)


def test_provider_config_has_required_fields():
    for p in PROVIDERS:
        assert p.name
        assert p.label
        assert isinstance(p.enabled, bool)
