"""Main dashboard page - live telescope status."""
import streamlit as st
import time

from utils.coordinates import format_ra, format_dec


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

    # Auto-refresh
    time.sleep(2)
    st.rerun()
