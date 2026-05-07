"""Focuser control page."""
import streamlit as st


def render_focus(alpaca):
    """Render focuser controls."""
    st.header("\U0001f52d Focuser Control")

    # Read current status
    try:
        status = alpaca.get_focuser_status()
        current_pos = status.get("position")
        temperature = status.get("temperature")
        max_step = status.get("maxstep", 2600)
    except Exception as e:
        st.error(f"Failed to read focuser status: {e}")
        return

    # Current status metrics
    col_pos, col_temp = st.columns(2)
    with col_pos:
        pos_str = f"{current_pos} / {max_step}" if current_pos is not None else "N/A"
        st.metric("Current Position", pos_str,
                  help=f"Focuser step position (range: 0\u2013{max_step}). "
                       f"0 = lens closest to sensor (infinity focus direction), "
                       f"{max_step} = lens furthest out. Best star focus is "
                       f"typically in the lower-to-middle range.")
    with col_temp:
        temp_str = f"{temperature:.1f}\u00b0C / {temperature * 9/5 + 32:.1f}\u00b0F" if temperature is not None else "N/A"
        st.metric("Temperature", temp_str,
                  help="Focuser/sensor temperature. Focus drifts as temperature changes "
                       "\u2014 re-focus if temp shifts more than 2-3\u00b0C.")

    st.divider()

    # Step buttons for fine/coarse adjustment
    st.subheader("Step Adjustment")
    st.caption("Fine (\u00b110) for dialing in sharp focus, coarse (\u00b1100) for large moves. "
               "Point at a bright star, take short exposures, and adjust until the star "
               "is the smallest, sharpest pinpoint.")
    cols = st.columns([1, 1, 1, 1, 2])

    if current_pos is not None:
        with cols[0]:
            if st.button("<< -100", use_container_width=True):
                resp = alpaca.move_focuser(current_pos - 100)
                if resp.success:
                    st.rerun()
                else:
                    st.error(resp.error_message)
        with cols[1]:
            if st.button("< -10", use_container_width=True):
                resp = alpaca.move_focuser(current_pos - 10)
                if resp.success:
                    st.rerun()
                else:
                    st.error(resp.error_message)
        with cols[2]:
            if st.button("> +10", use_container_width=True):
                resp = alpaca.move_focuser(current_pos + 10)
                if resp.success:
                    st.rerun()
                else:
                    st.error(resp.error_message)
        with cols[3]:
            if st.button(">> +100", use_container_width=True):
                resp = alpaca.move_focuser(current_pos + 100)
                if resp.success:
                    st.rerun()
                else:
                    st.error(resp.error_message)
    else:
        st.warning("Cannot read current position. Is the focuser connected?")

    st.divider()

    # Direct position input
    st.subheader("Move to Position")
    st.caption("Enter an exact focuser position to move to directly.")
    col_input, col_btn = st.columns([3, 1])
    with col_input:
        target = st.number_input(
            "Target Position",
            min_value=0,
            max_value=max_step,
            value=current_pos if current_pos is not None else 0,
            step=10,
            help=f"Absolute focuser step position (0\u2013{max_step}). "
                 f"If you know your best focus from a previous session, "
                 f"enter it here to return quickly.",
        )
    with col_btn:
        st.write("")  # spacing to align with input
        st.write("")
        if st.button("Move", type="primary", use_container_width=True):
            resp = alpaca.move_focuser(int(target))
            if resp.success:
                st.success(f"Moving to position {int(target)}...")
                st.rerun()
            else:
                st.error(f"Move failed: {resp.error_message}")
