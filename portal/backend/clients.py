"""Shared client instances for ALPACA and Stellarium

Imports the existing AlpacaClient and StellariumClient from the Streamlit codebase.
Provides singleton instances for the backend to use.
"""

import sys
from pathlib import Path

# Add existing_codebase to path to import clients
existing_code_path = Path(__file__).parent.parent / "existing_codebase"
sys.path.insert(0, str(existing_code_path))

from clients.alpaca_client import AlpacaClient
from clients.stellarium_client import StellariumClient
from backend.config import settings

# Singleton instances
_alpaca_client = None
_stellarium_client = None


def get_alpaca_client() -> AlpacaClient:
    """Get shared ALPACA client instance"""
    global _alpaca_client
    if _alpaca_client is None:
        _alpaca_client = AlpacaClient(host=settings.seestar_ip, port=settings.seestar_port)
    return _alpaca_client


def get_stellarium_client() -> StellariumClient:
    """Get shared Stellarium client instance"""
    global _stellarium_client
    if _stellarium_client is None:
        _stellarium_client = StellariumClient(
            host=settings.stellarium_host, port=settings.stellarium_port
        )
    return _stellarium_client
