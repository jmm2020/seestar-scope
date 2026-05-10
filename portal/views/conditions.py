"""Observing conditions page — astronomy + weather dashboard.

Reads from /api/conditions/{current,forecast}. Astronomy data renders even
when the weather API is unreachable (graceful degradation).
"""

import os
import time
import logging

import streamlit as st
import requests
import plotly.graph_objects as go

logger = logging.getLogger(__name__)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://seestar-portal-backend:8503")


def _check_backend_reachable() -> bool:
    try:
        resp = requests.get(f"{BACKEND_URL}/health", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


def _fetch_current() -> dict | None:
    try:
        resp = requests.get(f"{BACKEND_URL}/api/conditions/current", timeout=10)
        if resp.status_code == 200:
            return resp.json()
        logger.warning(f"/api/conditions/current returned {resp.status_code}")
    except Exception as e:
        logger.warning(f"Failed to fetch current conditions: {e}")
    return None


def _fetch_forecast(hours: int = 12) -> list[dict]:
    try:
        resp = requests.get(
            f"{BACKEND_URL}/api/conditions/forecast",
            params={"hours": hours},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning(f"/api/conditions/forecast returned {resp.status_code}")
    except Exception as e:
        logger.warning(f"Failed to fetch forecast: {e}")
    return []


def _twilight_label(astro: dict) -> tuple[str, str]:
    """Return (label, color) for twilight state."""
    if astro["is_astronomical_night"]:
        return ("Astronomical Night", "#22c55e")  # green — best
    if astro["is_nautical_twilight"]:
        return ("Nautical Twilight", "#facc15")  # yellow
    if astro["is_civil_twilight"]:
        return ("Civil Twilight", "#fb923c")  # orange
    if astro["sun_altitude_deg"] >= 0:
        return ("Daytime", "#ef4444")  # red — no observing
    return ("Pre-dark", "#fb923c")


def _moon_phase_label(illumination_pct: float) -> str:
    if illumination_pct < 5:
        return "New Moon"
    if illumination_pct < 40:
        return "Crescent"
    if illumination_pct < 60:
        return "Quarter"
    if illumination_pct < 95:
        return "Gibbous"
    return "Full Moon"


def render_conditions(config):
    """Main entry point — render observing conditions page."""
    st.title("\U0001f324️ Observing Conditions")
    st.caption(
        f"Site: {getattr(config, 'site_name', 'My Observatory')} "
        f"({getattr(config, 'site_latitude', 0):.2f}°, "
        f"{getattr(config, 'site_longitude', 0):.2f}°)"
    )

    if not _check_backend_reachable():
        st.error(f"⚠️ Backend API is not reachable at {BACKEND_URL}. Conditions data unavailable.")
        return

    # Auto-refresh + manual refresh controls
    col_a, col_b = st.columns([3, 1])
    with col_a:
        auto_refresh = st.checkbox("Auto-refresh every 60 seconds", value=False)
    with col_b:
        if st.button("\U0001f504 Refresh Now", use_container_width=True):
            st.rerun()

    st.divider()

    current = _fetch_current()
    if current is None:
        st.error("Could not fetch current conditions from backend.")
        return

    weather = current["weather"]
    astro = current["astro"]

    # --- Weather panel ---
    if not weather["weather_api_ok"]:
        st.warning("⚠️ Open-Meteo weather API unreachable — showing astronomical data only.")

    st.subheader("Current Conditions")
    w1, w2, w3, w4 = st.columns(4)

    cloud = weather["cloud_cover_pct"]
    wind = weather["wind_speed_ms"]
    humidity = weather["humidity_pct"]
    temp = weather["temperature_c"]

    w1.metric(
        "Cloud Cover",
        f"{cloud}%" if cloud is not None else "—",
        help="Lower is better — <20% is excellent for imaging",
    )
    w2.metric(
        "Wind",
        f"{wind:.1f} m/s" if wind is not None else "—",
        help="Wind speed at 10m above ground",
    )
    w3.metric(
        "Humidity",
        f"{humidity}%" if humidity is not None else "—",
        help="High humidity (>80%) increases dew risk",
    )
    w4.metric("Temperature", f"{temp:.1f} °C" if temp is not None else "—")

    st.divider()

    # --- Astro panel ---
    st.subheader("Astronomy")
    a1, a2, a3, a4 = st.columns(4)

    sun_alt = astro["sun_altitude_deg"]
    moon_alt = astro["moon_altitude_deg"]
    moon_ill = astro["moon_illumination_pct"]
    label, color = _twilight_label(astro)

    a1.metric(
        "Sun Altitude", f"{sun_alt:.1f}°", help="Sun position. Astronomical night begins at -18°."
    )
    moon_alt_label = f"{moon_alt:.1f}°" if moon_alt >= 0 else "Below horizon"
    a2.metric(
        "Moon Altitude",
        moon_alt_label,
        help="Moon position. Below horizon = no light pollution from moon.",
    )
    a3.metric(
        "Moon Phase",
        f"{moon_ill:.0f}% — {_moon_phase_label(moon_ill)}",
        help="Moon illumination percentage",
    )
    a4.metric("Twilight", label, help="Astronomical Night = darkest sky for deep-sky imaging")

    # Twilight badge with color
    st.markdown(
        f'<div style="padding:6px 14px;display:inline-block;border-radius:8px;'
        f"background:{color}22;border:1px solid {color}66;color:{color};"
        f'font-weight:600;letter-spacing:1px;">{label.upper()}</div>',
        unsafe_allow_html=True,
    )

    st.divider()

    # --- Forecast strip ---
    st.subheader("12-Hour Cloud Cover Forecast")
    forecast = _fetch_forecast(hours=12)
    if not forecast:
        st.info("Forecast unavailable.")
    else:
        any_weather = any(p["weather"]["weather_api_ok"] for p in forecast)
        if not any_weather:
            st.warning("Open-Meteo forecast unreachable.")
        else:
            xs = list(range(len(forecast)))
            ys = [p["weather"]["cloud_cover_pct"] or 0 for p in forecast]
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=ys,
                    mode="lines",
                    fill="tozeroy",
                    line=dict(color="#00c8ff", width=2),
                    name="Cloud cover %",
                )
            )
            fig.add_hline(
                y=20,
                line=dict(color="#22c55e", width=1, dash="dash"),
                annotation_text="20% (excellent)",
                annotation_position="top right",
            )
            fig.update_layout(
                xaxis_title="Hours from now",
                yaxis_title="Cloud cover (%)",
                yaxis=dict(range=[0, 100]),
                height=280,
                margin=dict(l=40, r=20, t=10, b=40),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(10,20,40,0.4)",
                font=dict(color="#c0d8ff"),
            )
            st.plotly_chart(fig, use_container_width=True)

    if auto_refresh:
        time.sleep(60)
        st.rerun()
