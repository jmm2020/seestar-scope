"""Siril Stacking View — Session-Oriented Stacking Pipeline UI

Streamlit interface for the StackingService. Mirrors the autofocus view:
backend health check → status poll → config panel → controls → result.
Calls FastAPI backend at BACKEND_URL/api/stacking/*.
"""

import logging
import os
import time
from typing import Any, Dict, Optional

import requests
import streamlit as st

logger = logging.getLogger(__name__)

# Backend API base URL (matches autofocus / platesolve views)
BACKEND_URL = os.environ.get("BACKEND_URL", "http://seestar-portal-backend:8503")


def render_stacking(alpaca, config):
    """Main stacking view rendering function.

    Args:
        alpaca: AlpacaClient instance (carried for API parity, not used here)
        config: Loaded portal config (carried for parity)
    """
    st.title("\U0001f9f2 Siril Stacking")
    st.markdown(
        "Session-oriented stacking pipeline: collect frames → process via Siril → "
        "stacked output saved to gallery."
    )

    if not check_backend_health():
        st.error(
            f"⚠️ Backend API is not reachable at {BACKEND_URL}. Start the FastAPI backend first."
        )
        st.code(
            "cd backend && uvicorn main:app --host 0.0.0.0 --port 8503",
            language="bash",
        )
        return

    status = get_stacking_status()
    if status is None:
        st.error("Failed to get stacking status from backend")
        return

    is_running = bool(status.get("running", False))
    latest_result = status.get("latest_result")

    if is_running:
        st.info("\U0001f504 **Stacking pipeline is running...** Please wait.")

    st.divider()

    render_config_panel(is_running)

    st.divider()

    render_session_controls(is_running, status)

    st.divider()

    render_status_display(status)

    st.divider()

    if latest_result:
        render_result(latest_result)
    else:
        st.info("No stacking results yet. Start a session and add frames above.")


# ---------------------------------------------------------------------------
# Backend client helpers
# ---------------------------------------------------------------------------


def check_backend_health() -> bool:
    """Check if FastAPI backend is reachable."""
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=2)
        return response.status_code == 200
    except Exception as exc:
        logger.debug("Backend health check failed: %s", exc)
        return False


def get_stacking_status() -> Optional[Dict[str, Any]]:
    """Fetch current stacking status from backend."""
    try:
        response = requests.get(f"{BACKEND_URL}/api/stacking/status", timeout=5)
        if response.status_code == 200:
            return response.json()
        logger.error("Failed to get stacking status: %s", response.status_code)
        return None
    except Exception as exc:
        logger.error("Error getting stacking status: %s", exc)
        return None


def get_default_config() -> Optional[Dict[str, Any]]:
    """Fetch default stacking config from backend."""
    try:
        response = requests.get(f"{BACKEND_URL}/api/stacking/config", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as exc:
        logger.error("Error getting default config: %s", exc)
        return None


# ---------------------------------------------------------------------------
# UI sections
# ---------------------------------------------------------------------------


def render_config_panel(is_running: bool) -> None:
    """Render the configuration form."""
    with st.expander("⚙️ Configuration", expanded=not is_running):
        if "stacking_config" not in st.session_state:
            cfg = get_default_config() or {
                "target_name": "target",
                "exposure_time": 10.0,
                "gain": 80,
                "dark_path": None,
                "flat_path": None,
                "bias_path": None,
                "sigma_low": 3.0,
                "sigma_high": 3.0,
            }
            st.session_state.stacking_config = cfg

        cfg = st.session_state.stacking_config

        col1, col2 = st.columns(2)
        with col1:
            target_name = st.text_input(
                "Target Name",
                value=cfg.get("target_name", "target"),
                disabled=is_running,
                help="Used in output filenames (e.g. m31_<session>.fit)",
            )
            exposure_time = st.number_input(
                "Exposure (s)",
                min_value=0.1,
                max_value=300.0,
                value=float(cfg.get("exposure_time", 10.0)),
                step=1.0,
                disabled=is_running,
                help="Per-frame exposure (metadata only)",
            )
            gain = st.number_input(
                "Gain",
                min_value=0,
                max_value=400,
                value=int(cfg.get("gain", 80)),
                step=10,
                disabled=is_running,
            )
        with col2:
            sigma_low = st.number_input(
                "Sigma Low",
                min_value=0.5,
                max_value=10.0,
                value=float(cfg.get("sigma_low", 3.0)),
                step=0.5,
                disabled=is_running,
                help="Lower-tail sigma rejection",
            )
            sigma_high = st.number_input(
                "Sigma High",
                min_value=0.5,
                max_value=10.0,
                value=float(cfg.get("sigma_high", 3.0)),
                step=0.5,
                disabled=is_running,
                help="Upper-tail sigma rejection",
            )

        with st.expander("Calibration (optional)", expanded=False):
            dark_path = st.text_input(
                "Master Dark",
                value=cfg.get("dark_path") or "",
                disabled=is_running,
                placeholder="/data/seestar/calibration/master_dark.fit",
            )
            flat_path = st.text_input(
                "Master Flat",
                value=cfg.get("flat_path") or "",
                disabled=is_running,
                placeholder="/data/seestar/calibration/master_flat.fit",
            )
            bias_path = st.text_input(
                "Master Bias",
                value=cfg.get("bias_path") or "",
                disabled=is_running,
                placeholder="/data/seestar/calibration/master_bias.fit",
            )

        st.session_state.stacking_config = {
            "target_name": target_name,
            "exposure_time": exposure_time,
            "gain": gain,
            "dark_path": dark_path or None,
            "flat_path": flat_path or None,
            "bias_path": bias_path or None,
            "sigma_low": sigma_low,
            "sigma_high": sigma_high,
        }


def render_session_controls(is_running: bool, status: Dict[str, Any]) -> None:
    """Render Start / Add Frame / Process / Abort controls."""
    session_id = status.get("session_id")
    has_session = bool(session_id)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button(
            "▶️ Start Session",
            disabled=is_running,
            use_container_width=True,
            type="primary",
        ):
            start_session(st.session_state.stacking_config)

    with col2:
        if st.button(
            "➕ Add Frame",
            disabled=is_running or not has_session,
            use_container_width=True,
        ):
            st.session_state.show_add_frame = True

    with col3:
        if st.button(
            "\U0001f680 Process Stack",
            disabled=is_running or not has_session or status.get("frame_count", 0) == 0,
            use_container_width=True,
        ):
            process_stack()

    with col4:
        if st.button(
            "⏹️ Abort",
            disabled=not is_running,
            use_container_width=True,
        ):
            abort_stacking()

    if st.session_state.get("show_add_frame"):
        with st.form("add_frame_form", clear_on_submit=True):
            frame_path = st.text_input(
                "Frame Path",
                placeholder="/data/seestar/captures/m31_001.png",
            )
            submitted = st.form_submit_button("Add")
            if submitted and frame_path:
                add_frame(frame_path)
                st.session_state.show_add_frame = False


def render_status_display(status: Dict[str, Any]) -> None:
    """Render running indicator, frame count, progress."""
    progress_value = max(0.0, min(1.0, float(status.get("progress", 0.0) or 0.0)))
    col1, col2, col3 = st.columns(3)

    with col1:
        running = status.get("running", False)
        st.metric("Running", "Yes" if running else "No")

    with col2:
        st.metric("Frame Count", status.get("frame_count", 0))

    with col3:
        st.metric("Progress", f"{int(progress_value * 100)}%")

    st.progress(progress_value)

    session_id = status.get("session_id")
    if session_id:
        st.caption(f"Session: `{session_id}`")


def render_result(result: Dict[str, Any]) -> None:
    """Render the latest stacking result."""
    success = bool(result.get("success", False))
    if success:
        st.success("✅ **Stacking Complete**")
    else:
        st.error("❌ **Stacking Failed**")
        err = result.get("error_message")
        if err:
            st.error(f"Error: {err}")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Frames Stacked", result.get("frame_count", 0))
    with col2:
        duration = result.get("duration_seconds", 0)
        st.metric("Duration", f"{duration:.1f}s")
    with col3:
        st.metric("Session", str(result.get("session_id", ""))[:8])

    output_fits = result.get("output_fits")
    output_jpeg = result.get("output_jpeg")

    if output_fits:
        st.markdown(f"**Stacked FITS:** `{output_fits}`")
    if output_jpeg:
        st.markdown(f"**Stacked JPEG:** `{output_jpeg}`")
        try:
            if os.path.exists(output_jpeg):
                st.image(output_jpeg, caption="Stacked output", use_container_width=True)
        except Exception as exc:
            logger.warning("Failed to display stacked image %s: %s", output_jpeg, exc)
            st.caption(f"Preview unavailable — open `{output_jpeg}` in the Gallery page.")

    st.info("View the stacked output in the **Gallery** page.")


# ---------------------------------------------------------------------------
# API actions
# ---------------------------------------------------------------------------


def start_session(cfg: Dict[str, Any]) -> None:
    """POST /start to create a new stacking session."""
    try:
        with st.spinner("Starting stacking session..."):
            response = requests.post(
                f"{BACKEND_URL}/api/stacking/start",
                json=cfg,
                timeout=10,
            )
        if response.status_code == 200:
            st.success("✅ Session started")
            st.rerun()
        elif response.status_code == 409:
            st.warning("Stacking is already running")
        else:
            st.error(f"Failed to start: {response.status_code} — {response.text}")
    except Exception as exc:
        logger.error("Error starting session: %s", exc)
        st.error(f"Error: {exc}")


def add_frame(path: str) -> None:
    """POST /add-frame to append a frame to the session."""
    try:
        with st.spinner("Adding frame..."):
            response = requests.post(
                f"{BACKEND_URL}/api/stacking/add-frame",
                json={"path": path},
                timeout=5,
            )
        if response.status_code == 200:
            st.success("✅ Frame added")
            st.rerun()
        elif response.status_code == 404:
            st.warning("No active session — start one first")
        else:
            st.error(f"Failed to add frame: {response.status_code} — {response.text}")
    except Exception as exc:
        logger.error("Error adding frame: %s", exc)
        st.error(f"Error: {exc}")


def process_stack() -> None:
    """POST /process and verify the background task actually started."""
    try:
        with st.spinner("Dispatching stacking pipeline..."):
            response = requests.post(
                f"{BACKEND_URL}/api/stacking/process",
                timeout=10,
            )
        if response.status_code != 200:
            st.error(f"Failed to start processing: {response.status_code} — {response.text}")
            return

        # FastAPI BackgroundTasks dispatches asynchronously; poll once to confirm the
        # background coroutine started before reporting success to the user.
        time.sleep(0.5)
        status = get_stacking_status()
        latest = status.get("latest_result") if status else None
        if status and (status.get("running") or (latest and latest.get("success"))):
            st.success("✅ Siril stacking started")
        else:
            st.warning("Dispatch succeeded but service is not yet running — check backend logs")
        st.rerun()
    except Exception as exc:
        logger.error("Error processing stack: %s", exc)
        st.error(f"Error: {exc}")


def abort_stacking() -> None:
    """POST /abort to stop the running pipeline."""
    try:
        with st.spinner("Aborting..."):
            response = requests.post(
                f"{BACKEND_URL}/api/stacking/abort",
                timeout=5,
            )
        if response.status_code == 200:
            st.success("✅ Abort signal sent")
            st.rerun()
        elif response.status_code == 404:
            st.warning("No stacking pipeline running")
        else:
            st.error(f"Failed to abort: {response.status_code}")
    except Exception as exc:
        logger.error("Error aborting: %s", exc)
        st.error(f"Error: {exc}")
