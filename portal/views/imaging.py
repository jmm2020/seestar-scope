"""Camera control, live view stream, and stacking controls page."""

import logging
import streamlit as st
import time

from utils.image_processing import alpaca_imagearray_to_image, save_image, apply_stretch

logger = logging.getLogger(__name__)

# Stage labels (shared with dashboard)
STAGE_LABELS = {
    "ContinuousExposure": "Live Preview",
    "Stack": "Stacking",
    "RTSP": "Video Stream",
    "AutoGoto": "Slewing",
    "3PPA": "Plate Solving",
}

MODE_LABELS = {
    "star": "Deep Sky",
    "moon": "Lunar",
    "sun": "Solar",
    "scenery": "Scenery",
    "planet": "Planetary",
}


# --- Live View ---


def _render_live_view(alpaca):
    """Embed the MJPEG stream from seestar_alp."""
    st.subheader("Live View")
    stream_url = alpaca.img_stream_url
    st.html(f'''
        <div style="width:100%; text-align:center; background:#0a0a0a;
                    border-radius:8px; overflow:hidden; padding:4px 0;">
            <img src="{stream_url}"
                 style="width:100%; max-height:70vh; object-fit:contain;"
                 alt="Seestar Live View"
                 onerror="this.style.display='none';
                          this.parentElement.innerHTML=
                          '<p style=\\'color:#888;padding:40px\\'>Stream unavailable &mdash; '
                          +'is seestar_alp running on port {alpaca._img_port}?</p>'" />
        </div>
    ''')


# --- Session Status ---


def _render_session_status(alpaca):
    """Show live stacking/view state with optional auto-poll."""
    st.subheader("Session Status")

    col_btn, col_auto = st.columns([1, 3])
    with col_btn:
        st.button("Update Status", key="btn_update_status", use_container_width=True)
    with col_auto:
        auto_poll = st.checkbox(
            "Auto-poll (5s)",
            key="auto_poll_status",
            help="Automatically refresh status every 5 seconds. "
            "Does NOT interrupt the live stream.",
        )

    view_data = alpaca.get_view_state()
    if not view_data:
        st.info("No view state available - Seestar may not be connected")
        return None, False

    view = view_data.get("View", view_data)
    state = view.get("state", "idle")
    mode = view.get("mode", "unknown")
    stage = view.get("stage", "unknown")
    target = view.get("target_name", "")
    gain = view.get("gain")
    lp_filter = view.get("lp_filter", False)
    is_stacking = stage == "Stack"

    # Get FPS and elapsed from stage-specific data
    stage_data = view.get(stage, {})
    fps = stage_data.get("fps")
    lapse_ms = view.get("lapse_ms", 0)
    elapsed_min = lapse_ms / 60000 if lapse_ms else 0

    # Frame count from Stack sub-dict
    stack_data = view.get("Stack", {})
    frame_count = stack_data.get("count", 0)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        state_display = "Working" if state == "working" else state.title()
        st.metric("State", state_display)
    with c2:
        st.metric("Mode", MODE_LABELS.get(mode, mode.title()))
    with c3:
        st.metric("Stage", STAGE_LABELS.get(stage, stage))
    with c4:
        st.metric("Gain", gain if gain is not None else "N/A")
    with c5:
        st.metric("LP Filter", "ON" if lp_filter else "OFF")
    with c6:
        if fps is not None:
            st.metric("FPS", f"{fps:.1f}")
        else:
            st.metric("FPS", "N/A")

    # Second row: elapsed, frames, target
    if is_stacking or elapsed_min > 0:
        c7, c8, c9 = st.columns(3)
        with c7:
            st.metric("Elapsed", f"{elapsed_min:.1f}m")
        with c8:
            st.metric("Frames", frame_count)
        with c9:
            st.metric("Target", target if target else "Manual")

    if auto_poll:
        time.sleep(5)
        st.rerun()

    return view, is_stacking


# --- Stacking Controls ---


def _render_stacking_controls(alpaca, view, is_stacking, alp_available: bool = True):
    """Gain, exposure, LP filter, and start/stop/restart buttons; disabled when alp_available is False."""
    st.subheader("Stacking Controls")

    current_gain = view.get("gain", 80) if view else 80

    col_gain, col_exp, col_lp = st.columns(3)
    with col_gain:
        gain = st.slider("Stack Gain", 0, 400, value=int(current_gain), step=1, key="stack_gain")
    with col_exp:
        st.number_input(
            "Exposure (ms)",
            min_value=1000,
            max_value=30000,
            value=10000,
            step=1000,
            key="stack_exp",
        )
    with col_lp:
        lp_on = view.get("lp_filter", False) if view else False
        lp_filter = st.checkbox("LP Filter", value=lp_on, key="stack_lp")

    col_start, col_stop, col_restart = st.columns(3)
    with col_start:
        if st.button(
            "Start Stack",
            type="primary",
            disabled=is_stacking or not alp_available,
            use_container_width=True,
            key="btn_start_stack",
        ):
            with st.spinner("Starting stack..."):
                alpaca.start_stack(restart=False, gain=gain)
                if lp_filter != lp_on:
                    alpaca.set_stack_lp_filter(lp_filter)
            # Auto-create session when stacking starts
            if st.session_state.get("active_session_id") is None:
                from clients.sessions_client import SessionsClient

                _sc = SessionsClient()
                target = st.session_state.get("slewing_target", "Unknown")
                session = _sc.start_session(target_name=target)
                if session:
                    st.session_state["active_session_id"] = session["id"]
                    logger.info(f"Session {session['id']} started for {target}")
            st.rerun()
    with col_stop:
        if st.button(
            "Stop Stack",
            disabled=not is_stacking or not alp_available,
            use_container_width=True,
            key="btn_stop_stack",
        ):
            with st.spinner("Stopping..."):
                alpaca.stop_stack()
            # End active session on stop
            sid = st.session_state.get("active_session_id")
            if sid is not None:
                from clients.sessions_client import SessionsClient

                _sc = SessionsClient()
                _sc.end_session(sid)
                st.session_state["active_session_id"] = None
                logger.info(f"Session {sid} ended")
            st.rerun()
    with col_restart:
        if st.button(
            "Restart Stack",
            disabled=not alp_available,
            use_container_width=True,
            key="btn_restart_stack",
        ):
            with st.spinner("Restarting stack..."):
                alpaca.stop_stack()
                time.sleep(1)
                alpaca.start_stack(restart=True, gain=gain)
                if lp_filter != lp_on:
                    alpaca.set_stack_lp_filter(lp_filter)
            st.rerun()

    # Apply gain change if user adjusted slider while stacking
    if is_stacking:
        if st.button(
            "Apply Gain",
            key="btn_apply_stack_gain",
            help="Send current slider value to the Seestar without restarting",
        ):
            alpaca.set_stack_gain(gain)
            st.success(f"Gain set to {gain}")


# --- Stack Settings (Expander) ---


def _render_stack_settings(alpaca):
    """Expandable panel for stack processing options and dither."""
    with st.expander("Stack Settings", expanded=False):
        # Fetch current settings
        dev_state = alpaca.get_device_state()
        settings = dev_state.get("setting", {}) if dev_state else {}
        stack_cfg = settings.get("stack", {})
        dither_cfg = settings.get("stack_dither", {})

        st.caption("Processing Options")
        c1, c2, c3 = st.columns(3)
        with c1:
            dbe = st.checkbox(
                "DBE (Background Extraction)", value=stack_cfg.get("dbe", True), key="opt_dbe"
            )
            star_corr = st.checkbox(
                "Star Correction", value=stack_cfg.get("star_correction", True), key="opt_star_corr"
            )
        with c2:
            airplane = st.checkbox(
                "Airplane Removal",
                value=stack_cfg.get("airplane_line_removal", False),
                key="opt_airplane",
            )
            drizzle = st.checkbox(
                "Drizzle 2x", value=stack_cfg.get("drizzle2x", False), key="opt_drizzle"
            )
        with c3:
            save_ok = st.checkbox(
                "Save OK Frames",
                value=stack_cfg.get("save_discrete_ok_frame", True),
                key="opt_save_ok",
            )
            save_all = st.checkbox(
                "Save All Frames",
                value=stack_cfg.get("save_discrete_frame", False),
                key="opt_save_all",
            )

        st.caption("Dither Settings")
        cd1, cd2, cd3 = st.columns(3)
        with cd1:
            dither_en = st.checkbox(
                "Enable Dither", value=dither_cfg.get("enable", True), key="opt_dither_en"
            )
        with cd2:
            dither_pix = st.number_input(
                "Dither Pixels",
                min_value=10,
                max_value=500,
                value=dither_cfg.get("pix", 100),
                step=10,
                key="opt_dither_pix",
            )
        with cd3:
            dither_int = st.number_input(
                "Dither Interval",
                min_value=1,
                max_value=50,
                value=dither_cfg.get("interval", 5),
                step=1,
                key="opt_dither_int",
            )

        if st.button("Apply Settings", use_container_width=True, key="btn_apply_settings"):
            with st.spinner("Applying..."):
                alpaca.set_stack_setting("dbe", dbe)
                alpaca.set_stack_setting("star_correction", star_corr)
                alpaca.set_stack_setting("airplane_line_removal", airplane)
                alpaca.set_stack_setting("drizzle2x", drizzle)
                alpaca.set_stack_setting("save_discrete_ok_frame", save_ok)
                alpaca.set_stack_setting("save_discrete_frame", save_all)
                alpaca.set_stack_dither(dither_en, dither_pix, dither_int)
            st.success("Stack settings applied")


# --- Camera Status (existing) ---

CAMERA_STATES = {
    0: "Idle",
    1: "Waiting",
    2: "Exposing",
    3: "Reading",
    4: "Download",
    5: "Error",
}


def _render_camera_status(alpaca):
    """Show current camera state and settings."""
    try:
        cam = alpaca.get_camera_status()
        state_code = cam.get("state_code")
        state_text = cam.get("state", "Unknown")
        gain = cam.get("gain")

        col_state, col_gain, col_filter = st.columns(3)
        with col_state:
            st.metric(
                "Camera State",
                state_text,
                help="Idle = ready, Exposing = capturing light, "
                "Reading = transferring from sensor, Error = problem detected",
            )
        with col_gain:
            st.metric(
                "Current Gain",
                gain if gain is not None else "N/A",
                help="Sony IMX462 sensor gain (0-400). Higher = brighter but noisier.",
            )
        with col_filter:
            try:
                names = alpaca.get_filter_names()
                pos = alpaca.get_filter_position()
                current = (
                    names[pos] if names and pos is not None and pos < len(names) else "Unknown"
                )
            except Exception:
                current = "N/A"
            st.metric(
                "Filter",
                current,
                help="Active filter: Dark = no filter, IR = infrared cut, LP = light pollution",
            )

        return state_code
    except Exception as e:
        st.error(f"Camera status error: {e}")
        return None


# --- Single Frame Capture (existing) ---


def _render_exposure_controls(alpaca):
    """Exposure time, gain, and filter controls."""
    st.subheader("Exposure Settings")
    st.caption("Adjust exposure time, sensor gain, and filter.")

    try:
        cam = alpaca.get_camera_status()
        hw_gain = cam.get("gain")
        if hw_gain is not None and "gain_slider" not in st.session_state:
            st.session_state["gain_slider"] = int(hw_gain)
    except Exception:
        pass

    try:
        filter_names = alpaca.get_filter_names()
    except Exception:
        filter_names = ["Dark", "IR", "LP"]

    try:
        hw_filter_pos = alpaca.get_filter_position()
        if hw_filter_pos is not None and "filter_select" not in st.session_state:
            st.session_state["filter_select"] = int(hw_filter_pos)
    except Exception:
        pass

    col_exp, col_gain, col_filter = st.columns(3)

    with col_exp:
        exposure = st.number_input(
            "Exposure (seconds)",
            min_value=0.001,
            max_value=2000.0,
            value=st.session_state.get("img_exposure", 10.0),
            step=1.0,
            format="%.3f",
            key="exposure_input",
        )
        st.session_state["img_exposure"] = exposure

    with col_gain:
        gain = st.slider("Gain", min_value=0, max_value=400, step=1, key="gain_slider")
        if st.button("Set Gain", key="apply_gain", use_container_width=True):
            resp = alpaca.set_gain(gain)
            if resp.success:
                st.rerun()
            else:
                st.error(f"Set gain failed: {resp.error_message}")

    with col_filter:
        filter_choice = st.selectbox(
            "Filter",
            options=list(range(len(filter_names))),
            format_func=lambda i: filter_names[i] if i < len(filter_names) else f"Filter {i}",
            key="filter_select",
        )
        if st.button("Set Filter", key="apply_filter", use_container_width=True):
            resp = alpaca.set_filter(filter_choice)
            if resp.success:
                st.rerun()
            else:
                st.error(f"Set filter failed: {resp.error_message}")

    return exposure, gain


def _render_capture_controls(alpaca, exposure):
    """Capture, Abort, and Loop mode controls."""
    st.subheader("Capture")

    col_cap, col_abort, col_loop = st.columns([2, 1, 2])

    with col_cap:
        if st.button("Capture", type="primary", use_container_width=True, key="btn_capture"):
            resp = alpaca.start_exposure(exposure, light=True)
            if resp.success:
                st.session_state["exposing"] = True
                st.session_state["exposure_start"] = time.time()
                st.session_state["exposure_duration"] = exposure
                st.rerun()
            else:
                st.error(f"Capture failed: {resp.error_message}")

    with col_abort:
        if st.button("Abort", use_container_width=True, key="btn_abort"):
            resp = alpaca.abort_exposure()
            if resp.success:
                st.session_state["exposing"] = False
                st.warning("Exposure aborted")
            else:
                st.error(f"Abort failed: {resp.error_message}")

    with col_loop:
        loop_enabled = st.checkbox("Loop Mode", key="loop_mode")
        if loop_enabled:
            frame_count = st.number_input(
                "Frames",
                min_value=1,
                max_value=999,
                value=st.session_state.get("loop_frames", 10),
                step=1,
                key="frame_count_input",
            )
            st.session_state["loop_frames"] = frame_count
            completed = st.session_state.get("loop_completed", 0)
            st.caption(f"Completed: {completed} / {frame_count}")


def _poll_exposure(alpaca):
    """Poll camera state during exposure and show progress."""
    if not st.session_state.get("exposing"):
        return

    try:
        cam = alpaca.get_camera_status()
        state_code = cam.get("state_code")
        state_text = cam.get("state", "Unknown")
    except Exception:
        return

    duration = st.session_state.get("exposure_duration", 10)
    elapsed = time.time() - st.session_state.get("exposure_start", time.time())

    if state_code == 2:  # Exposing
        progress = min(elapsed / max(duration, 0.001), 0.99)
        remaining = max(duration - elapsed, 0)
        st.progress(progress, text=f"Exposing... {remaining:.1f}s remaining")
        time.sleep(1)
        st.rerun()
    elif state_code in (1, 3, 4):  # Waiting, Reading, Download
        st.info(f"Camera: {state_text}")
        time.sleep(0.5)
        st.rerun()
    elif state_code == 0:  # Idle - check if image ready
        if alpaca.is_image_ready():
            st.session_state["exposing"] = False
            st.session_state["image_ready"] = True
            st.rerun()
        else:
            time.sleep(0.5)
            st.rerun()
    elif state_code == 5:  # Error
        st.session_state["exposing"] = False
        st.error("Camera reported an error during exposure")


def _render_preview_and_save(alpaca, config):
    """Download image, show preview, and offer save."""
    if not st.session_state.get("image_ready"):
        return

    if "last_image" not in st.session_state:
        with st.spinner("Downloading image from camera..."):
            image_data = alpaca.get_image_array()
            if image_data:
                image = alpaca_imagearray_to_image(image_data)
                if image:
                    st.session_state["last_image"] = image
                    st.session_state["image_ready"] = False
                else:
                    st.error("Failed to convert image data")
                    st.session_state["image_ready"] = False
                    return
            else:
                st.error("Failed to download image from camera")
                st.session_state["image_ready"] = False
                return

    image = st.session_state.get("last_image")
    if image is None:
        return

    st.subheader("Preview")

    use_stretch = st.checkbox("Apply histogram stretch", value=True, key="stretch_toggle")
    display_image = apply_stretch(image) if use_stretch else image
    st.image(display_image, caption="Captured Image", use_container_width=True)

    col_name, col_save = st.columns([3, 1])
    with col_name:
        target_name = st.text_input(
            "Target name for filename",
            value=st.session_state.get("slewing_target", "capture"),
            key="save_target_name",
        )
    with col_save:
        st.write("")
        st.write("")
        if st.button("Save Image", type="primary", key="btn_save", use_container_width=True):
            save_dir = getattr(config, "save_directory", "./captures")
            filepath = save_image(image, target_name, save_dir=save_dir)
            st.success(f"Saved: {filepath}")
            # Log frame to active session
            sid = st.session_state.get("active_session_id")
            if sid is not None:
                from clients.sessions_client import SessionsClient

                _sc = SessionsClient()
                _sc.add_frame(
                    session_id=sid,
                    filename=str(filepath),
                    exposure_s=st.session_state.get("img_exposure", 10.0),
                    gain=st.session_state.get("gain_slider", 80),
                    filter_name="Unknown",
                )

    # Handle loop mode
    if st.session_state.get("loop_mode"):
        completed = st.session_state.get("loop_completed", 0) + 1
        st.session_state["loop_completed"] = completed
        total = st.session_state.get("loop_frames", 10)

        save_dir = getattr(config, "save_directory", "./captures")
        target_name = st.session_state.get("slewing_target", "loop")
        filepath = save_image(image, f"{target_name}_frame{completed}", save_dir=save_dir)
        st.caption(f"Auto-saved frame {completed}: {filepath}")

        if completed < total:
            st.session_state.pop("last_image", None)
            exposure = st.session_state.get("img_exposure", 10.0)
            resp = alpaca.start_exposure(exposure, light=True)
            if resp.success:
                st.session_state["exposing"] = True
                st.session_state["exposure_start"] = time.time()
                st.session_state["exposure_duration"] = exposure
                time.sleep(0.5)
                st.rerun()
            else:
                st.error(f"Loop capture failed on frame {completed + 1}: {resp.error_message}")
        else:
            st.success(f"Loop complete: {completed} frames captured")
            st.session_state["loop_completed"] = 0


# --- Main Page ---


def render_imaging(alpaca, config):
    """Render the camera imaging page."""
    st.header("\U0001f4f7 Camera & Imaging")

    alp_available = alpaca.is_alp_available()
    if not alp_available:
        st.error(
            f"⚠️ **seestar_alp is not reachable** at `{alpaca.alp_base_url}` — "
            "live view and stacking are non-functional until the service is running."
        )

    if "active_session_id" not in st.session_state:
        st.session_state["active_session_id"] = None

    # Live MJPEG stream
    _render_live_view(alpaca)

    st.divider()

    # Session status with auto-poll
    view, is_stacking = _render_session_status(alpaca)

    st.divider()

    # Stacking controls
    _render_stacking_controls(alpaca, view, is_stacking, alp_available)

    # Stack settings expander
    _render_stack_settings(alpaca)

    st.divider()

    # Existing camera status and single-frame capture in expanders
    with st.expander("Camera Status", expanded=False):
        _render_camera_status(alpaca)

    with st.expander("Single Frame Capture", expanded=False):
        exposure, gain = _render_exposure_controls(alpaca)
        _render_capture_controls(alpaca, exposure)
        _poll_exposure(alpaca)
        _render_preview_and_save(alpaca, config)
