"""Data-driven auth provider list.

Add a ProviderConfig entry and set enabled=True to activate a provider
without touching account.py.  Currently enabled: email, google.
Disabled (reserved): apple, github.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class ProviderConfig:
    name: str
    label: str
    icon: str
    enabled: bool


PROVIDERS: List[ProviderConfig] = [
    ProviderConfig(name="email", label="Email / Password", icon="✉️", enabled=True),
    ProviderConfig(name="google", label="Continue with Google", icon="G", enabled=True),
    ProviderConfig(name="apple", label="Continue with Apple", icon="", enabled=False),
    ProviderConfig(name="github", label="Continue with GitHub", icon="", enabled=False),
]


def get_enabled_providers() -> List[ProviderConfig]:
    return [p for p in PROVIDERS if p.enabled]


def get_oauth_providers() -> List[ProviderConfig]:
    """Return enabled OAuth providers (excludes 'email')."""
    return [p for p in get_enabled_providers() if p.name != "email"]
