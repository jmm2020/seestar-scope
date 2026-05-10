"""Live Status Dashboard - Real-time telescope, camera, and focuser monitoring

Displays live status from ALPACA client with auto-refresh.
Shows telescope position (RA/Dec, Alt/Az), camera state/temperature, focuser position.
Updates every 2 seconds using st.rerun() for real-time monitoring.
"""

import os
import streamlit as st
import requests
import logging
import time

logger = logging.getLogger(__name__)

# Backend API base URL
BACKEND_URL = os.environ.get("BACKEND_URL", "http://seestar-portal-backend:8503")


def render_live_status(alpaca):
    """Main live status dashboard rendering function."""
    st.title("☄️ Live Status Dashboard")
    st.markdown("Real-time telescope, camera, and focuser monitoring with auto-refresh")

    # Check backend connectivity
    backend_healthy = check_backend_health()
    if not backend_healthy:
        st.warning(
            f"⚠️ Backend API is not reachable at {BACKEND_URL}. Live WebSocket connection count unavailable."
        )

    # Auto-refresh controls
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("**Auto-refresh every 2 seconds** — live data from ALPACA client")
    with col2:
        # Show WebSocket connection count if backend available
        if backend_healthy:
            try:
                response = requests.get(f"{BACKEND_URL}/api/status/connections", timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    conn_count = data.get("active_connections", 0)
                    st.metric("🔗 WS Clients", conn_count)
            except Exception as e:
                logger.debug(f"Could not fetch connection count: {e}")

    st.divider()

    # Create placeholder containers for live updates
    telescope_container = st.empty()
    camera_container = st.empty()
    focuser_container = st.empty()

    # Fetch and display live status
    render_telescope_status(alpaca, telescope_container)
    render_camera_status(alpaca, camera_container)
    render_focuser_status(alpaca, focuser_container)

    # Auto-refresh trigger
    time.sleep(2)
    st.rerun()


def check_backend_health() -> bool:
    """Check if FastAPI backend is reachable."""
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def render_telescope_status(alpaca, container):
    """Display real-time telescope position and state."""
    try:
        status = alpaca.get_telescope_status()

        with container.container():
            st.markdown("### 🔭 Telescope")

            if not status.get("connected", False):
                st.error("❌ Telescope not connected")
                return

            # Position metrics
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                ra = status.get("ra")
                if ra is not None:
                    ra_hours = ra / 15.0  # Convert degrees to hours
                    st.metric("RA", f"{ra_hours:.4f}h")
                else:
                    st.metric("RA", "N/A")

            with col2:
                dec = status.get("dec")
                if dec is not None:
                    st.metric("Dec", f"{dec:.4f}°")
                else:
                    st.metric("Dec", "N/A")

            with col3:
                alt = status.get("altitude")
                if alt is not None:
                    st.metric("Altitude", f"{alt:.2f}°")
                else:
                    st.metric("Altitude", "N/A")

            with col4:
                az = status.get("azimuth")
                if az is not None:
                    st.metric("Azimuth", f"{az:.2f}°")
                else:
                    st.metric("Azimuth", "N/A")

            # State indicators
            col1, col2, col3 = st.columns(3)

            with col1:
                tracking = status.get("tracking", False)
                icon = "🟢" if tracking else "🔴"
                st.markdown(f"{icon} **Tracking:** {'ON' if tracking else 'OFF'}")

            with col2:
                slewing = status.get("slewing", False)
                icon = "🟡" if slewing else "⚪"
                st.markdown(f"{icon} **Slewing:** {'YES' if slewing else 'NO'}")

            with col3:
                at_park = status.get("at_park", False)
                icon = "🅿️" if at_park else "🔓"
                st.markdown(f"{icon} **Parked:** {'YES' if at_park else 'NO'}")

    except Exception as e:
        logger.error(f"Error fetching telescope status: {e}")
        with container.container():
            st.error(f"⚠️ Error: {str(e)}")


def render_camera_status(alpaca, container):
    """Display real-time camera state and temperature."""
    try:
        status = alpaca.get_camera_status()

        with container.container():
            st.markdown("### 📷 Camera")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                state = status.get("state", "unknown")
                state_map = {
                    "idle": ("⚪", "Idle"),
                    "exposing": ("🟢", "Exposing"),
                    "reading": ("🟡", "Reading"),
                    "download": ("🔵", "Download"),
                    "error": ("🔴", "Error"),
                    "unknown": ("❓", "Unknown"),
                }
                icon, label = state_map.get(state.lower(), ("❓", state.title()))
                st.markdown(f"{icon} **State:** {label}")

            with col2:
                temp = status.get("temperature")
                if temp is not None:
                    st.metric("Sensor Temp", f"{temp:.1f}°C")
                else:
                    st.metric("Sensor Temp", "N/A")

            with col3:
                cooler_on = status.get("cooler_on", False)
                icon = "❄️" if cooler_on else "🔥"
                st.markdown(f"{icon} **Cooler:** {'ON' if cooler_on else 'OFF'}")

            with col4:
                gain = status.get("gain")
                if gain is not None:
                    st.metric("Gain", f"{gain}")
                else:
                    st.metric("Gain", "N/A")

    except Exception as e:
        logger.error(f"Error fetching camera status: {e}")
        with container.container():
            st.error(f"⚠️ Camera error: {str(e)}")


def render_focuser_status(alpaca, container):
    """Display real-time focuser position and movement state."""
    try:
        status = alpaca.get_focuser_status()

        with container.container():
            st.markdown("### 🎯 Focuser")

            col1, col2, col3 = st.columns(3)

            with col1:
                position = status.get("position")
                if position is not None:
                    st.metric("Position", f"{position} steps")
                else:
                    st.metric("Position", "N/A")

            with col2:
                is_moving = status.get("is_moving", False)
                icon = "🔄" if is_moving else "⏸️"
                st.markdown(f"{icon} **Moving:** {'YES' if is_moving else 'NO'}")

            with col3:
                temp = status.get("temperature")
                if temp is not None:
                    st.metric("Temperature", f"{temp:.1f}°C")
                else:
                    st.metric("Temperature", "N/A")

    except Exception as e:
        logger.error(f"Error fetching focuser status: {e}")
        with container.container():
            st.error(f"⚠️ Focuser error: {str(e)}")
