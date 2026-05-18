"""Data-driven auth provider list.

v1 providers: email, google (enabled=True).
v1.1+ providers listed but disabled — set enabled=True to activate
without touching account.py.
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
