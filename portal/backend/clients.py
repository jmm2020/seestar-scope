"""Shared client instances for ALPACA and Stellarium.

Imports AlpacaClient and StellariumClient from the canonical portal/clients/
package (the same code Streamlit uses) and provides singletons for the backend.
"""

from clients.alpaca_client import AlpacaClient
from clients.stellarium_client import StellariumClient
from backend.config import settings

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
