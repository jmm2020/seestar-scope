"""SeestarScope - Seestar S50 Telescope Control Web Application.

Main Streamlit entry point with sidebar navigation and page routing.
"""
import streamlit as st
import logging

from config_loader import load_config
from clients.alpaca_client import AlpacaClient
from clients.stellarium_client import StellariumClient
from views.theme import (
    inject_cosmic_css,
    render_sidebar_brand,
    render_connection_status,
    render_nav_radio,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration - must be first Streamlit call
st.set_page_config(
    page_title="SeestarScope",
    page_icon="\U0001f52d",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject cosmic theme
inject_cosmic_css()

# --- Session State Initialization ---

if "config" not in st.session_state:
    st.session_state.config = load_config()

config = st.session_state.config

if "alpaca" not in st.session_state:
    st.session_state.alpaca = AlpacaClient(
        host=config.seestar_ip,
        port=config.seestar_port,
    )

if "stellarium" not in st.session_state:
    st.session_state.stellarium = StellariumClient(
        host=config.stellarium_host,
        port=config.stellarium_port,
    )

if "connected" not in st.session_state:
    st.session_state.connected = False

alpaca = st.session_state.alpaca
stellarium = st.session_state.stellarium

# --- Auto-connect on first load ---

if not st.session_state.connected and config.auto_connect:
    with st.spinner("\U0001f52d Connecting to Seestar S50..."):
        results = alpaca.connect_all()
        st.session_state.connected = True
        success_count = sum(1 for v in results.values() if v)
        if success_count == 5:
            logger.info("All 5 ALPACA devices connected")
        else:
            failed = [k for k, v in results.items() if not v]
            logger.warning(f"Failed to connect: {', '.join(failed)}")

# --- Sidebar ---

with st.sidebar:
    render_sidebar_brand()

    st.divider()

    # Connection status with icons
    if st.session_state.connected:
        render_connection_status(alpaca, stellarium)
    else:
        st.warning("Not connected")

    if st.button("\u26a1 Reconnect All", use_container_width=True):
        results = alpaca.connect_all()
        st.session_state.connected = True
        st.rerun()

    st.divider()

    # Page navigation with icons
    page = render_nav_radio()

# --- Page Routing ---

if page == "Dashboard":
    from views.dashboard import render_dashboard
    render_dashboard(alpaca, stellarium)

elif page == "GoTo":
    from views.goto import render_goto
    render_goto(alpaca, stellarium)

elif page == "Imaging":
    from views.imaging import render_imaging
    render_imaging(alpaca, config)

elif page == "Focus":
    from views.focus import render_focus
    render_focus(alpaca)

elif page == "Autofocus":
    from views.autofocus import render_autofocus
    render_autofocus(alpaca)

elif page == "Plate Solve":
    from views.platesolve import render_platesolve
    render_platesolve()

elif page == "Sequence":
    from views.sequence import render_sequence
    render_sequence(alpaca, stellarium)

elif page == "Gallery":
    from views.gallery import render_gallery
    render_gallery()

elif page == "Live Status":
    from views.live_status import render_live_status
    render_live_status(alpaca)

elif page == "Settings":
    from views.settings import render_settings
    render_settings(config, alpaca, stellarium)
