"""Main dashboard page - live telescope status + native device telemetry."""
import streamlit as st
import time
import logging

from utils.coordinates import format_ra, format_dec

logger = logging.getLogger(__name__)


def render_dashboard(alpaca, stellarium):
    """Render the main status dashboard."""
    st.header("\u2604\ufe0f Seestar S50 Dashboard")
    st.caption("Live view \u2014 auto-refreshes every 2 seconds")

    # Connection status row
    cols = st.columns(5)
    for i, device in enumerate(["telescope", "camera", "focuser", "filterwheel", "switch"]):
        connected = alpaca.connected_devices.get(device, False)
        cols[i].metric(
            device.title(),
            "Connected" if connected else "Disconnected",
            delta=None,
            help=f"ALPACA {device} device (DeviceNumber 0)",
        )

    st.divider()

    # Telescope status and Camera/Sensors side by side
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Mount")
        try:
            status = alpaca.get_telescope_status()
            if status["ra"] is not None:
                st.metric("Right Ascension", format_ra(status["ra"]),
                          help="Current RA in J2000 epoch (hours, minutes, seconds)")
                st.metric("Declination", format_dec(status["dec"]),
                          help="Current Dec in J2000 epoch (degrees, arcmin, arcsec)")
                st.metric("Tracking", "ON" if status["tracking"] else "OFF",
                          help="Sidereal tracking compensates for Earth's rotation")

                status_text = []
                if status["slewing"]:
                    status_text.append("SLEWING")
                if status["at_home"]:
                    status_text.append("HOME")
                if status["at_park"]:
                    status_text.append("PARKED")
                st.metric("Status", " | ".join(status_text) if status_text else "Ready",
                          help="Ready = idle, SLEWING = moving to target, PARKED = safe position")
            else:
                st.warning("Telescope not responding")
        except Exception as e:
            st.error(f"Could not read telescope status: {e}")

    with col2:
        st.subheader("Camera & Sensors")
        try:
            cam = alpaca.get_camera_status()
            st.metric("Camera State", cam["state"],
                      help="Idle, Exposing, Reading, Download, or Error")
            st.metric("Gain", cam["gain"],
                      help="Sony IMX462 sensor gain (0\u2013400). Higher = brighter but noisier")
        except Exception as e:
            st.error(f"Camera status error: {e}")

        try:
            focus = alpaca.get_focuser_status()
            st.metric("Focuser Position", focus["position"],
                      help="Relative focuser step position (lower = closer to sensor)")
            temp = focus["temperature"]
            temp_str = f"{temp:.1f}\u00b0C / {temp * 9/5 + 32:.1f}\u00b0F" if temp is not None else "N/A"
            st.metric("Temperature", temp_str,
                      help="Focuser/sensor temperature \u2014 affects focus drift over time")
        except Exception as e:
            st.error(f"Focuser status error: {e}")

        try:
            filter_names = alpaca.get_filter_names()
            filter_pos = alpaca.get_filter_position()
            current_filter = filter_names[filter_pos] if filter_names and filter_pos is not None and filter_pos < len(filter_names) else "Unknown"
            st.metric("Filter", current_filter,
                      help="Dark = no filter, IR = infrared cut, LP = light pollution")
        except Exception as e:
            st.error(f"Filter wheel error: {e}")

        try:
            dew = alpaca.get_dew_heater()
            st.metric("Dew Heater", "ON" if dew else "OFF",
                      help="Prevents condensation on the lens in humid conditions")
        except Exception as e:
            st.error(f"Dew heater error: {e}")

    # --- Native Device Telemetry ---
    st.divider()
    _render_device_health(alpaca)

    # --- View State ---
    st.divider()
    _render_view_state(alpaca)

    # Stellarium connection status
    st.divider()
    st.subheader("Stellarium")
    if stellarium.is_available():
        obj = stellarium.get_selected_object()
        if obj:
            st.success(f"Selected: **{obj.name}** ({obj.object_type}) in {obj.constellation}")
            st.write(f"RA: {format_ra(obj.ra_j2000_hours)} | "
                     f"Dec: {format_dec(obj.dec_j2000_degrees)} | "
                     f"Alt: {obj.altitude:.1f}\u00b0 | Mag: {obj.magnitude:.1f}")
            if obj.above_horizon:
                if st.button("Slew to Selected Object", type="primary",
                             help="Send a GoTo command to slew the telescope to this object"):
                    resp = alpaca.slew_to(obj.ra_j2000_hours, obj.dec_j2000_degrees)
                    if resp.success:
                        st.session_state["slewing_target"] = obj.name
                    else:
                        st.error(f"Slew failed: {resp.error_message}")
            else:
                st.warning(f"{obj.name} is below the horizon")
        else:
            st.info("No object selected in Stellarium. Click on something in the sky map.")
    else:
        st.warning("Stellarium Remote Control not available on port 8091. "
                   "Enable it in Stellarium: Configuration > Plugins > Remote Control.")

    # Auto-refresh controls
    st.divider()
    col_refresh, col_auto = st.columns([1, 3])
    with col_refresh:
        if st.button("Refresh Now", key="dash_refresh", use_container_width=True):
            st.rerun()
    with col_auto:
        auto_refresh = st.checkbox("Auto-refresh (5s)", value=False,
                                   help="Enable automatic refresh every 5 seconds. "
                                        "Disabled by default to prevent flickering.")
    if auto_refresh:
        time.sleep(5)
        st.rerun()


def _render_device_health(alpaca):
    """Display native Seestar device health — battery, WiFi, storage, sensors."""
    st.subheader("Device Health")
    try:
        state = alpaca.get_device_state()
        if not state:
            st.warning("Could not fetch device state (seestar_alp may not support method_sync)")
            return

        # --- Row 1: Power & Connectivity ---
        col_batt, col_wifi, col_storage, col_temp = st.columns(4)

        # Battery
        pi = state.get("pi_status", {})
        with col_batt:
            batt_pct = pi.get("battery_capacity")
            charge = pi.get("charger_status", "Unknown")
            if batt_pct is not None:
                # Color-coded label
                if batt_pct >= 50:
                    batt_icon = "\U0001f7e2"  # green circle
                elif batt_pct >= 20:
                    batt_icon = "\U0001f7e1"  # yellow circle
                else:
                    batt_icon = "\U0001f534"  # red circle
                st.metric("Battery", f"{batt_pct}%",
                          help=f"Charge status: {charge}")
                st.progress(batt_pct / 100)
                charging = pi.get("charge_online", False)
                batt_temp = pi.get("battery_temp")
                caption_parts = [charge]
                if batt_temp is not None:
                    caption_parts.append(f"{batt_temp}\u00b0C")
                st.caption(f"{batt_icon} {' | '.join(caption_parts)}")
            else:
                st.metric("Battery", "N/A")

        # WiFi
        station = state.get("station", {})
        with col_wifi:
            sig = station.get("sig_lev")
            if sig is not None:
                # Convert dBm to approximate percentage
                # -30 dBm = excellent (100%), -90 dBm = unusable (0%)
                wifi_pct = max(0, min(100, int((sig + 90) * 100 / 60)))
                st.metric("WiFi Signal", f"{sig} dBm",
                          help=f"Connected to: {station.get('ssid', 'Unknown')}")
                st.progress(wifi_pct / 100)
                ssid = station.get("ssid", "Unknown")
                ip = station.get("ip", "")
                st.caption(f"{ssid} | {ip}")
            else:
                st.metric("WiFi Signal", "N/A")

        # Storage
        storage = state.get("storage", {})
        with col_storage:
            volumes = storage.get("storage_volume", [])
            if volumes:
                vol = volumes[0]
                free_mb = vol.get("free_mb", 0)
                total_mb = vol.get("total_mb", 1)
                used_pct = vol.get("used_percent", 0)
                free_gb = free_mb / 1024
                total_gb = total_mb / 1024
                st.metric("Free Storage", f"{free_gb:.1f} GB",
                          help=f"Total: {total_gb:.1f} GB")
                st.progress(1.0 - (used_pct / 100))  # Show free as progress
                st.caption(f"{100 - used_pct}% free of {total_gb:.0f} GB")
            else:
                st.metric("Free Storage", "N/A")

        # CPU Temperature
        with col_temp:
            cpu_temp = pi.get("temp")
            if cpu_temp is not None:
                # Temperature warning thresholds
                if cpu_temp >= 70:
                    temp_icon = "\U0001f534"  # red
                elif cpu_temp >= 55:
                    temp_icon = "\U0001f7e1"  # yellow
                else:
                    temp_icon = "\U0001f7e2"  # green
                st.metric("CPU Temp", f"{cpu_temp:.1f}\u00b0C",
                          help="Seestar processor temperature. >70\u00b0C may cause throttling.")
                is_over = pi.get("is_overtemp", False)
                st.caption(f"{temp_icon} {'OVERTEMP!' if is_over else 'Normal'}")
            else:
                st.metric("CPU Temp", "N/A")

        # --- Row 2: Sensors & Device Info ---
        col_balance, col_compass, col_mount, col_info = st.columns(4)

        # Balance sensor
        balance = state.get("balance_sensor", {})
        with col_balance:
            bdata = balance.get("data", {})
            angle = bdata.get("angle")
            if angle is not None:
                if angle <= 5:
                    lvl_icon = "\U0001f7e2"
                elif angle <= 15:
                    lvl_icon = "\U0001f7e1"
                else:
                    lvl_icon = "\U0001f534"
                st.metric("Tilt Angle", f"{angle:.1f}\u00b0",
                          help="Leveling sensor. <5\u00b0 is good for equatorial mode.")
                st.caption(f"{lvl_icon} {'Level' if angle <= 5 else 'Tilted'}")
            else:
                st.metric("Tilt Angle", "N/A")

        # Compass
        compass = state.get("compass_sensor", {})
        with col_compass:
            cdata = compass.get("data", {})
            direction = cdata.get("direction")
            if direction is not None:
                # Cardinal direction
                cardinals = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
                idx = int((direction + 22.5) / 45) % 8
                cardinal = cardinals[idx]
                st.metric("Compass", f"{direction:.1f}\u00b0 {cardinal}",
                          help="Magnetic heading from the internal compass sensor")
            else:
                st.metric("Compass", "N/A")

        # Mount info
        mount = state.get("mount", {})
        with col_mount:
            equ = mount.get("equ_mode", False)
            closed = mount.get("close", False)
            mode = "Equatorial" if equ else "Alt-Az"
            arm = "Closed" if closed else "Open"
            st.metric("Mount Mode", mode,
                      help="Equatorial mode enables better tracking for long exposures")
            st.caption(f"Arm: {arm} | Tracking: {'ON' if mount.get('tracking') else 'OFF'}")

        # Device info
        device = state.get("device", {})
        setting = state.get("setting", {})
        with col_info:
            fw = device.get("firmware_ver_string", "Unknown")
            model = device.get("product_model", "Seestar")
            focal = setting.get("focal_pos", "N/A")
            st.metric("Firmware", f"v{fw}",
                      help=f"{model} | SN: {device.get('sn', 'N/A')}")
            st.caption(f"Focal: {focal} | f/{device.get('fnumber', '?')} {device.get('focal_len', '?')}mm")

    except Exception as e:
        logger.error(f"Device health error: {e}")
        st.warning(f"Could not load device telemetry: {e}")


def _render_view_state(alpaca):
    """Display current imaging/view state from native Seestar API."""
    st.subheader("Session Status")
    try:
        view_data = alpaca.get_view_state()
        if not view_data:
            st.info("No active view state")
            return

        view = view_data.get("View", {})
        if not view:
            st.info("Idle \u2014 no active session")
            return

        state = view.get("state", "idle")
        mode = view.get("mode", "unknown")
        stage = view.get("stage", "unknown")
        target = view.get("target_name", "unknown")
        gain = view.get("gain")
        lp_filter = view.get("lp_filter", False)

        col_state, col_mode, col_stage, col_target = st.columns(4)

        with col_state:
            if state == "working":
                st.metric("State", "Working", help="Seestar is actively imaging")
            elif state == "idle":
                st.metric("State", "Idle")
            else:
                st.metric("State", state.title())

        with col_mode:
            mode_labels = {"star": "Deep Sky", "moon": "Lunar", "sun": "Solar",
                           "scenery": "Scenery", "planet": "Planetary"}
            st.metric("Mode", mode_labels.get(mode, mode.title()),
                      help=f"Raw mode: {mode}")

        with col_stage:
            stage_labels = {
                "ContinuousExposure": "Live Preview",
                "Stack": "Stacking",
                "RTSP": "Video Stream",
                "AutoGoto": "Slewing",
                "3PPA": "Plate Solving",
            }
            st.metric("Stage", stage_labels.get(stage, stage),
                      help=f"Raw stage: {stage}")

        with col_target:
            st.metric("Target", target if target != "unknown" else "Manual",
                      help="Named target from catalog or 'Manual' for custom coordinates")

        # Extra detail row
        col_gain, col_filter, col_fps, col_elapsed = st.columns(4)

        with col_gain:
            if gain is not None:
                st.metric("Session Gain", gain)

        with col_filter:
            st.metric("LP Filter", "ON" if lp_filter else "OFF",
                      help="Light pollution filter")

        with col_fps:
            # Get FPS from the active stage data
            stage_data = view.get(stage, {})
            fps = stage_data.get("fps")
            if fps is not None:
                st.metric("FPS", f"{fps:.1f}")

        with col_elapsed:
            lapse_ms = view.get("lapse_ms", 0)
            if lapse_ms > 0:
                mins = lapse_ms / 60000
                if mins >= 60:
                    st.metric("Elapsed", f"{mins / 60:.1f}h")
                else:
                    st.metric("Elapsed", f"{mins:.0f}m")

    except Exception as e:
        logger.error(f"View state error: {e}")
        st.info("View state unavailable")
