"""Camera control and image capture page."""
import streamlit as st
import time

from utils.image_processing import alpaca_imagearray_to_image, save_image, apply_stretch

# Camera state labels from ALPACA spec
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
            st.metric("Camera State", state_text,
                      help="Idle = ready, Exposing = capturing light, "
                           "Reading = transferring from sensor, Error = problem detected")
        with col_gain:
            st.metric("Current Gain", gain if gain is not None else "N/A",
                      help="Sony IMX462 sensor gain (0-400). Higher = brighter "
                           "but noisier. This shows the value currently set on the camera.")
        with col_filter:
            try:
                names = alpaca.get_filter_names()
                pos = alpaca.get_filter_position()
                current = names[pos] if names and pos is not None and pos < len(names) else "Unknown"
            except Exception:
                current = "N/A"
            st.metric("Filter", current,
                      help="Active filter: Dark = no filter (darks/bias), "
                           "IR = infrared cut (visual), LP = light pollution")

        return state_code
    except Exception as e:
        st.error(f"Camera status error: {e}")
        return None


def _render_exposure_controls(alpaca):
    """Exposure time, gain, and filter controls."""
    st.subheader("Exposure Settings")
    st.caption("Adjust exposure time, sensor gain, and filter. Click Set Gain / Set Filter to send changes to the camera.")

    # Sync widget defaults from hardware on first visit
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
            help="Duration of each exposure. 0.001-1s for planets/moon, "
                 "5-30s for deep sky, up to 2000s for very faint targets.",
        )
        st.session_state["img_exposure"] = exposure

    with col_gain:
        gain = st.slider(
            "Gain",
            min_value=0,
            max_value=400,
            step=1,
            key="gain_slider",
            help="Sensor amplification. 0-80 = low noise (deep sky), "
                 "80-200 = balanced, 200-400 = bright but noisy (planets).",
        )
        if st.button("Set Gain", key="apply_gain", use_container_width=True,
                     help="Send the selected gain value to the camera hardware."):
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
        if st.button("Set Filter", key="apply_filter", use_container_width=True,
                     help="Switch the physical filter wheel to the selected position."):
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
        if st.button("Capture", type="primary", use_container_width=True,
                      key="btn_capture",
                      help="Start a single exposure with the current settings. "
                           "The image will appear in Preview when done."):
            resp = alpaca.start_exposure(exposure, light=True)
            if resp.success:
                st.session_state["exposing"] = True
                st.session_state["exposure_start"] = time.time()
                st.session_state["exposure_duration"] = exposure
                st.rerun()
            else:
                st.error(f"Capture failed: {resp.error_message}")

    with col_abort:
        if st.button("Abort", use_container_width=True, key="btn_abort",
                     help="Stop the current exposure immediately. "
                          "Partial data will be discarded."):
            resp = alpaca.abort_exposure()
            if resp.success:
                st.session_state["exposing"] = False
                st.warning("Exposure aborted")
            else:
                st.error(f"Abort failed: {resp.error_message}")

    with col_loop:
        loop_enabled = st.checkbox("Loop Mode", key="loop_mode",
                                   help="Automatically capture multiple frames in sequence. "
                                        "Images are auto-saved to the capture directory.")
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

    # Show progress bar for exposing state
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
            # Brief idle between states
            time.sleep(0.5)
            st.rerun()
    elif state_code == 5:  # Error
        st.session_state["exposing"] = False
        st.error("Camera reported an error during exposure")


def _render_preview_and_save(alpaca, config):
    """Download image, show preview, and offer save."""
    if not st.session_state.get("image_ready"):
        return

    # Download image if we haven't already
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

    # Stretch toggle
    use_stretch = st.checkbox("Apply histogram stretch", value=True,
                              key="stretch_toggle",
                              help="Stretch the image histogram to reveal faint detail. "
                                   "Uncheck to see the raw unprocessed image.")
    display_image = apply_stretch(image) if use_stretch else image
    st.image(display_image, caption="Captured Image", use_container_width=True)

    # Save controls
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
        if st.button("Save Image", type="primary", key="btn_save",
                      use_container_width=True):
            save_dir = getattr(config, "save_directory", "./captures")
            filepath = save_image(image, target_name, save_dir=save_dir)
            st.success(f"Saved: {filepath}")

    # Handle loop mode: trigger next frame
    if st.session_state.get("loop_mode"):
        completed = st.session_state.get("loop_completed", 0) + 1
        st.session_state["loop_completed"] = completed
        total = st.session_state.get("loop_frames", 10)

        # Auto-save in loop mode
        save_dir = getattr(config, "save_directory", "./captures")
        target_name = st.session_state.get("slewing_target", "loop")
        filepath = save_image(image, f"{target_name}_frame{completed}",
                              save_dir=save_dir)
        st.caption(f"Auto-saved frame {completed}: {filepath}")

        if completed < total:
            # Clear image and start next exposure
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
                st.error(f"Loop capture failed on frame {completed + 1}: "
                         f"{resp.error_message}")
        else:
            st.success(f"Loop complete: {completed} frames captured")
            st.session_state["loop_completed"] = 0


def render_imaging(alpaca, config):
    """Render the camera imaging page."""
    st.header("\U0001f4f7 Camera & Imaging")

    # Current status
    _render_camera_status(alpaca)

    st.divider()

    # Exposure settings
    exposure, gain = _render_exposure_controls(alpaca)

    st.divider()

    # Capture controls
    _render_capture_controls(alpaca, exposure)

    # Exposure progress polling
    _poll_exposure(alpaca)

    st.divider()

    # Image preview and save
    _render_preview_and_save(alpaca, config)
