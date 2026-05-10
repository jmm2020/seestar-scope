"""Plate Solving View - Astrometric plate solving via ASTAP

Provides blind and hint-based plate solving to verify telescope pointing accuracy.
Shows solved RA/Dec, field rotation, pixel scale, and offset from expected position.
"""

import os
import streamlit as st
import requests
from datetime import datetime
from typing import Dict, Any, Optional
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Backend API base URL
BACKEND_URL = os.environ.get("BACKEND_URL", "http://seestar-portal-backend:8503")


def render_platesolve():
    """Main plate solving view rendering function."""
    st.title("🎯 Plate Solving")
    st.markdown("Astrometric plate solving to verify telescope pointing accuracy")

    # Check backend connectivity
    if not check_backend_health():
        st.error(
            f"⚠️ Backend API is not reachable at {BACKEND_URL}. Start the FastAPI backend first."
        )
        st.code("cd backend && uvicorn main:app --host 0.0.0.0 --port 8503", language="bash")
        return

    col1, col2 = st.columns(2)

    with col1:
        render_solve_controls()

    with col2:
        render_session_history()


def check_backend_health() -> bool:
    """Check if FastAPI backend is reachable."""
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def render_solve_controls():
    """Render plate solving configuration and execution controls."""
    st.markdown("### 🔍 Solve Configuration")

    # Mode selector
    mode = st.radio(
        "Solving Mode",
        ["hint", "blind"],
        format_func=lambda x: (
            "🎯 Hint Mode (with position)" if x == "hint" else "🌌 Blind Mode (full-sky search)"
        ),
        help="Hint mode is faster when telescope position is known",
    )

    st.divider()

    # Image source selector
    image_source = st.radio(
        "Image Source",
        ["file_path", "upload"],
        format_func=lambda x: "📂 File Path" if x == "file_path" else "📤 Upload File",
        horizontal=True,
    )

    image_path = None
    uploaded_file = None

    if image_source == "file_path":
        image_path = st.text_input(
            "Image Path",
            placeholder="/data/seestar/images/m31_001.fits",
            help="Path to FITS or image file on server",
        )
    else:
        uploaded_file = st.file_uploader(
            "Upload Image",
            type=["fits", "fit", "png", "jpg", "jpeg"],
            help="Upload FITS or image file for plate solving",
        )

    st.divider()

    # Mode-specific parameters
    if mode == "hint":
        st.markdown("**Position Hint**")

        col_ra, col_dec = st.columns(2)

        with col_ra:
            expected_ra_hours = st.number_input(
                "Expected RA (hours)",
                min_value=0.0,
                max_value=24.0,
                value=0.0,
                step=0.1,
                format="%.4f",
                help="Right Ascension in decimal hours (0-24)",
            )

        with col_dec:
            expected_dec_degrees = st.number_input(
                "Expected Dec (degrees)",
                min_value=-90.0,
                max_value=90.0,
                value=0.0,
                step=1.0,
                format="%.4f",
                help="Declination in decimal degrees (-90 to +90)",
            )

        search_radius_deg = st.slider(
            "Search Radius (degrees)",
            min_value=1.0,
            max_value=15.0,
            value=5.0,
            step=0.5,
            help="Search radius around hint position",
        )

    # Optional parameters (both modes)
    with st.expander("⚙️ Advanced Options"):
        col_fov, col_ds = st.columns(2)

        with col_fov:
            fov_deg = st.number_input(
                "FOV Hint (degrees)",
                min_value=0.0,
                max_value=10.0,
                value=1.2,
                step=0.1,
                help="Field of view estimate (Seestar S50: ~1.23°)",
            )

        with col_ds:
            downsample = st.selectbox(
                "Downsample",
                [0, 1, 2, 3, 4],
                format_func=lambda x: "Auto" if x == 0 else f"{x}x{x}",
                help="Downsample factor (0=auto, 2=2x2, etc.)",
            )

    st.divider()

    # Solve button
    solve_button = st.button(
        "🚀 Solve Image",
        type="primary",
        use_container_width=True,
        disabled=not (image_path or uploaded_file),
    )

    if solve_button:
        if uploaded_file:
            execute_solve_upload(
                uploaded_file,
                mode,
                expected_ra_hours if mode == "hint" else None,
                expected_dec_degrees if mode == "hint" else None,
                search_radius_deg if mode == "hint" else None,
                fov_deg,
                downsample,
            )
        else:
            execute_solve_path(
                image_path,
                mode,
                expected_ra_hours if mode == "hint" else None,
                expected_dec_degrees if mode == "hint" else None,
                search_radius_deg if mode == "hint" else None,
                fov_deg,
                downsample,
            )


def execute_solve_path(
    image_path: str,
    mode: str,
    expected_ra_hours: Optional[float],
    expected_dec_degrees: Optional[float],
    search_radius_deg: Optional[float],
    fov_deg: float,
    downsample: int,
):
    """Execute plate solve for file path."""
    request_data = {
        "mode": mode,
        "image_path": image_path,
        "fov_deg": fov_deg if fov_deg > 0 else None,
        "downsample": downsample,
    }

    if mode == "hint":
        request_data["expected_ra_hours"] = expected_ra_hours
        request_data["expected_dec_degrees"] = expected_dec_degrees
        request_data["search_radius_deg"] = search_radius_deg

    with st.spinner("🔄 Solving..."):
        try:
            response = requests.post(
                f"{BACKEND_URL}/api/platesolve/solve", json=request_data, timeout=180
            )

            if response.status_code == 200:
                result = response.json()
                st.session_state["latest_solve_result"] = result
                display_solve_result(result)
            else:
                error_detail = response.json().get("detail", response.text)
                st.error(f"❌ Solve failed: {error_detail}")
                logger.error(f"Plate solve failed: {response.status_code} - {error_detail}")

        except requests.exceptions.Timeout:
            st.error("⏱️ Solve timeout (>180s). Try hint mode or downsample=2.")
        except Exception as e:
            st.error(f"❌ Error: {e}")
            logger.exception(f"Plate solve error: {e}")


def execute_solve_upload(
    uploaded_file,
    mode: str,
    expected_ra_hours: Optional[float],
    expected_dec_degrees: Optional[float],
    search_radius_deg: Optional[float],
    fov_deg: float,
    downsample: int,
):
    """Execute plate solve for uploaded file."""
    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}

    form_data = {
        "mode": mode,
        "fov_deg": fov_deg if fov_deg > 0 else None,
        "downsample": downsample,
    }

    if mode == "hint":
        form_data["expected_ra_hours"] = expected_ra_hours
        form_data["expected_dec_degrees"] = expected_dec_degrees
        form_data["search_radius_deg"] = search_radius_deg

    with st.spinner("🔄 Uploading and solving..."):
        try:
            response = requests.post(
                f"{BACKEND_URL}/api/platesolve/solve/upload",
                files=files,
                data=form_data,
                timeout=180,
            )

            if response.status_code == 200:
                result = response.json()
                st.session_state["latest_solve_result"] = result
                display_solve_result(result)
            else:
                error_detail = response.json().get("detail", response.text)
                st.error(f"❌ Solve failed: {error_detail}")
                logger.error(f"Plate solve failed: {response.status_code} - {error_detail}")

        except requests.exceptions.Timeout:
            st.error("⏱️ Solve timeout (>180s). Try hint mode or downsample=2.")
        except Exception as e:
            st.error(f"❌ Error: {e}")
            logger.exception(f"Plate solve error: {e}")


def display_solve_result(result: Dict[str, Any]):
    """Display plate solving result with metrics and details."""
    status = result.get("status")

    if status == "success":
        st.success("✅ Solve successful!")

        solution = result.get("solution")
        if solution:
            # Key metrics
            st.markdown("### 📊 Solution")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                ra_hours = solution["ra_hours"]
                ra_hms = hours_to_hms(ra_hours)
                st.metric("RA", ra_hms, help=f"{ra_hours:.6f} hours")

            with col2:
                dec_deg = solution["dec_degrees"]
                dec_dms = degrees_to_dms(dec_deg)
                st.metric("Dec", dec_dms, help=f"{dec_deg:.6f}°")

            with col3:
                st.metric("Rotation", f"{solution['rotation_deg']:.2f}°")

            with col4:
                st.metric("Pixel Scale", f"{solution['pixel_scale']:.2f}″/px")

            # Additional details
            col5, col6, col7 = st.columns(3)

            with col5:
                st.metric("FOV Width", f"{solution['fov_width']:.3f}°")

            with col6:
                st.metric("FOV Height", f"{solution['fov_height']:.3f}°")

            with col7:
                st.metric("Stars Matched", solution["num_stars"])

            # Offset display (hint mode only)
            if result.get("mode") == "hint" and result.get("offset_arcsec") is not None:
                st.divider()
                st.markdown("### 🎯 Pointing Accuracy")

                offset_arcsec = result["offset_arcsec"]

                col_offset1, col_offset2, col_offset3 = st.columns(3)

                with col_offset1:
                    st.metric(
                        "Total Offset",
                        f"{offset_arcsec:.1f}″",
                        help="Angular separation from expected position",
                    )

                with col_offset2:
                    st.metric("RA Offset", f"{result.get('offset_ra_arcsec', 0):.1f}″")

                with col_offset3:
                    st.metric("Dec Offset", f"{result.get('offset_dec_arcsec', 0):.1f}″")

                # Offset interpretation
                if offset_arcsec < 30:
                    st.success("🎯 Excellent pointing accuracy! Offset <30 arcsec.")
                elif offset_arcsec < 60:
                    st.warning("⚠️ Moderate offset. Consider recalibration if >1 arcmin.")
                else:
                    st.error(
                        "❌ Large offset detected. Telescope may need polar alignment or calibration."
                    )

        # Solve time
        if result.get("solve_time_sec"):
            st.caption(f"⏱️ Solved in {result['solve_time_sec']:.1f}s")

    elif status == "failed":
        st.error(f"❌ Solve failed: {result.get('error_message', 'Unknown error')}")

    elif status == "timeout":
        st.error("⏱️ Solve timeout. Try hint mode or increase downsample factor.")

    else:
        st.warning(f"ℹ️ Solve status: {status}")


def render_session_history():
    """Render session history with expandable details."""
    st.markdown("### 📜 Session History")

    try:
        response = requests.get(f"{BACKEND_URL}/api/platesolve/sessions", timeout=5)

        if response.status_code == 200:
            sessions_data = response.json()
            session_ids = sessions_data.get("sessions", [])

            if not session_ids:
                st.info("No plate solving sessions yet. Run a solve to get started!")
                return

            st.caption(f"**{sessions_data.get('count', 0)} sessions**")

            # Display recent sessions (last 10)
            for session_id in session_ids[-10:]:
                render_session_card(session_id)

        else:
            st.warning("Could not load session history")

    except Exception as e:
        logger.error(f"Failed to fetch session history: {e}")
        st.error(f"Error loading history: {e}")


def render_session_card(session_id: str):
    """Render a single session card with expandable details."""
    try:
        response = requests.get(f"{BACKEND_URL}/api/platesolve/result/{session_id}", timeout=5)

        if response.status_code == 200:
            result = response.json()

            status = result.get("status")
            mode = result.get("mode")
            timestamp = result.get("timestamp")

            # Status icon
            status_icon = {"success": "✅", "failed": "❌"}.get(status, "⏱️")
            mode_badge = "🎯 Hint" if mode == "hint" else "🌌 Blind"

            with st.expander(
                f"{status_icon} {session_id[:12]}... • {mode_badge} • {format_timestamp(timestamp)}"
            ):
                # Image path
                st.markdown(f"**Image:** `{Path(result['image_path']).name}`")

                if status == "success" and result.get("solution"):
                    solution = result["solution"]

                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown(f"**RA:** {hours_to_hms(solution['ra_hours'])}")
                        st.markdown(f"**Dec:** {degrees_to_dms(solution['dec_degrees'])}")
                        st.markdown(f"**Rotation:** {solution['rotation_deg']:.2f}°")

                    with col2:
                        st.markdown(f"**Pixel Scale:** {solution['pixel_scale']:.2f}″/px")
                        st.markdown(
                            f"**FOV:** {solution['fov_width']:.3f}° × {solution['fov_height']:.3f}°"
                        )
                        st.markdown(f"**Stars:** {solution['num_stars']}")

                    # Offset (hint mode)
                    if mode == "hint" and result.get("offset_arcsec") is not None:
                        st.divider()
                        st.markdown(
                            f"**Offset:** {result['offset_arcsec']:.1f}″ (RA: {result.get('offset_ra_arcsec', 0):.1f}″, Dec: {result.get('offset_dec_arcsec', 0):.1f}″)"
                        )

                    # Solve time
                    if result.get("solve_time_sec"):
                        st.caption(f"Solved in {result['solve_time_sec']:.1f}s")

                elif status == "failed":
                    st.error(f"Error: {result.get('error_message', 'Unknown error')}")

                elif status == "timeout":
                    st.warning("Solve timeout (>120s)")

    except Exception as e:
        logger.error(f"Failed to fetch session {session_id}: {e}")


def hours_to_hms(hours: float) -> str:
    """Convert decimal hours to HH:MM:SS format."""
    h = int(hours)
    m = int((hours - h) * 60)
    s = ((hours - h) * 60 - m) * 60
    return f"{h:02d}h {m:02d}m {s:05.2f}s"


def degrees_to_dms(degrees: float) -> str:
    """Convert decimal degrees to DD:MM:SS format."""
    sign = "+" if degrees >= 0 else "-"
    degrees = abs(degrees)
    d = int(degrees)
    m = int((degrees - d) * 60)
    s = ((degrees - d) * 60 - m) * 60
    return f"{sign}{d:02d}° {m:02d}' {s:05.2f}\""


def format_timestamp(timestamp_str: str) -> str:
    """Format ISO timestamp to readable string."""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return dt.strftime("%m/%d %H:%M:%S")
    except Exception:
        return timestamp_str[:16] if timestamp_str else ""
