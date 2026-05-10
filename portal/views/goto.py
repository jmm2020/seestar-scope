"""GoTo/Slew control page with Stellarium integration and catalog search."""

import streamlit as st
import requests
import time
import json
import logging
import os

from utils.coordinates import format_ra, format_dec, parse_ra, parse_dec
from catalog.messier import lookup_messier, search_catalog

logger = logging.getLogger(__name__)

# seestar_alp ALPACA bridge — sends real commands to the Seestar via JSON-RPC.
# Resolve from env so this works both on a developer host (defaults to localhost)
# and inside Docker containers where ALP runs as a separate service on the
# compose network (ALP_HOST=seestar-alp, ALP_PORT=5555).
SEESTAR_ALP_URL = (
    f"http://{os.environ.get('ALP_HOST', 'localhost')}:{os.environ.get('ALP_PORT', '5555')}"
)

# Seconds to wait for a scope state transition after dispatching a command.
# Increase if your scope is slow to respond (e.g. on a cold boot).
try:
    VERIFY_TIMEOUT_S = int(os.environ.get("SCOPE_VERIFY_TIMEOUT", "15"))
except ValueError:
    logger.warning("SCOPE_VERIFY_TIMEOUT is not a valid integer; defaulting to 15s")
    VERIFY_TIMEOUT_S = 15


def _seestar_action(method: str, params: dict = None, async_mode: bool = True) -> dict:
    """Send a JSON-RPC command to the Seestar via seestar_alp's action endpoint.

    Uses method_async by default (fire-and-forget) because the Seestar firmware
    often doesn't send response IDs back, causing method_sync to timeout after 10s.
    Set async_mode=False to wait for a response (may timeout).
    """
    payload = {"method": method}
    if params:
        payload.update(params)
    action = "method_async" if async_mode else "method_sync"
    try:
        resp = requests.put(
            f"{SEESTAR_ALP_URL}/api/v1/telescope/1/action",
            data={
                "Action": action,
                "Parameters": json.dumps(payload),
                "ClientID": "1",
                "ClientTransactionID": "999",
            },
            timeout=30,
        )
        result = resp.json()
        if result.get("ErrorNumber", 0) != 0:
            return {"success": False, "error": result.get("ErrorMessage", "Unknown error")}
        return {"success": True, "data": result}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": f"seestar_alp not reachable at {SEESTAR_ALP_URL}"}
    except Exception as e:
        logger.error(f"seestar_action({method}) failed: {e}")
        return {"success": False, "error": str(e)}


def _check_alp_reachable() -> bool:
    """Probe seestar-alp with a 2-second GET to detect service-down early."""
    try:
        resp = requests.get(
            f"{SEESTAR_ALP_URL}/management/v1/description",
            timeout=2,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _poll_state_transition(alpaca, predicate, timeout_s: int = VERIFY_TIMEOUT_S) -> bool:
    """Poll telescope state until predicate returns True or timeout_s elapses.

    Returns True if the transition was observed, False on timeout.
    Polls every 1 second; each GET to the ALPACA bridge is fast (~50ms).
    Exceptions from get_telescope_status() are caught and retried — a False
    return therefore means either no transition or the bridge was unreachable.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            status = alpaca.get_telescope_status()
            if predicate(status):
                return True
        except Exception as exc:
            logger.debug("_poll_state_transition: status read failed: %s", exc)
        time.sleep(1)
    return False


# Popular quick-access targets
QUICK_TARGETS = [
    ("M42", "Orion Nebula"),
    ("M31", "Andromeda Galaxy"),
    ("M45", "Pleiades"),
    ("M51", "Whirlpool Galaxy"),
    ("M13", "Great Globular"),
    ("M57", "Ring Nebula"),
    ("M27", "Dumbbell Nebula"),
    ("M81", "Bode's Galaxy"),
    ("M1", "Crab Nebula"),
    ("M104", "Sombrero Galaxy"),
    ("M101", "Pinwheel Galaxy"),
    ("M8", "Lagoon Nebula"),
]


def _slew_and_report(alpaca, ra_hours: float, dec_degrees: float, target_name: str):
    """Issue slew command and display result."""
    resp = alpaca.slew_to(ra_hours, dec_degrees)
    if resp.success:
        st.session_state["slewing_target"] = target_name
        st.rerun()
    else:
        st.error(f"Slew failed: {resp.error_message}")


def _render_slewing_progress(alpaca):
    """Poll telescope.slewing and show progress indicator."""
    try:
        status = alpaca.get_telescope_status()
        if status.get("slewing"):
            target = st.session_state.get("slewing_target", "target")
            st.info(f"Slewing to {target}...")
            progress = st.empty()
            progress.progress(50, text="Slewing in progress...")
            time.sleep(1)
            st.rerun()
    except Exception:
        pass


def _render_current_position(alpaca):
    """Display current telescope position."""
    st.subheader("Current Position")
    try:
        status = alpaca.get_telescope_status()
        if status["ra"] is not None:
            col_ra, col_dec, col_track, col_status = st.columns(4)
            with col_ra:
                st.metric(
                    "RA",
                    format_ra(status["ra"]),
                    help="Right Ascension in J2000 epoch (hours:min:sec)",
                )
            with col_dec:
                st.metric(
                    "Dec",
                    format_dec(status["dec"]),
                    help="Declination in J2000 epoch (degrees:arcmin:arcsec)",
                )
            with col_track:
                st.metric(
                    "Tracking",
                    "ON" if status["tracking"] else "OFF",
                    help="Sidereal tracking compensates for Earth's rotation "
                    "to keep objects centered",
                )
            with col_status:
                if status["slewing"]:
                    st.metric("Status", "SLEWING", help="Telescope is moving to a new target")
                elif status["at_park"]:
                    st.metric("Status", "PARKED", help="Telescope is in its safe park position")
                elif status["at_home"]:
                    st.metric("Status", "HOME", help="Telescope is at its home reference position")
                else:
                    st.metric("Status", "Ready", help="Telescope is idle and ready for commands")
        else:
            st.warning("Telescope not responding")
    except Exception as e:
        st.error(f"Could not read position: {e}")


def _render_manual_input(alpaca):
    """Manual RA/Dec input with Slew button."""
    st.subheader("Manual Coordinates")
    col_ra, col_dec, col_btn = st.columns([2, 2, 1])
    with col_ra:
        ra_text = st.text_input(
            "RA (hours)",
            placeholder="5:35:17 or 5.588",
            help="HH:MM:SS, HHh MMm SSs, or decimal hours",
            key="manual_ra",
        )
    with col_dec:
        dec_text = st.text_input(
            "Dec (degrees)",
            placeholder="-5:23:28 or -5.391",
            help="+/-DD:MM:SS or decimal degrees",
            key="manual_dec",
        )
    with col_btn:
        st.write("")  # spacing
        st.write("")
        slew_manual = st.button("Slew", type="primary", key="slew_manual", use_container_width=True)

    if slew_manual and ra_text and dec_text:
        try:
            ra = parse_ra(ra_text)
            dec = parse_dec(dec_text)
            if not (0 <= ra < 24):
                st.error("RA must be between 0 and 24 hours")
            elif not (-90 <= dec <= 90):
                st.error("Dec must be between -90 and +90 degrees")
            else:
                _slew_and_report(alpaca, ra, dec, f"RA {format_ra(ra)}")
        except ValueError:
            st.error("Invalid coordinate format. Use HH:MM:SS or decimal.")


def _render_stellarium_panel(alpaca, stellarium):
    """Stellarium selected-object panel with Slew button."""
    st.subheader("Stellarium")
    if not stellarium.is_available():
        st.warning("Stellarium Remote Control not available on port 8091")
        return

    obj = stellarium.get_selected_object()
    if not obj:
        st.info("No object selected in Stellarium. Click on something in the sky map.")
        return

    col_info, col_coords, col_btn = st.columns([3, 3, 1])
    with col_info:
        st.markdown(f"**{obj.name}** ({obj.object_type})")
        st.caption(f"Constellation: {obj.constellation} | Mag: {obj.magnitude:.1f}")
    with col_coords:
        st.markdown(f"RA: {format_ra(obj.ra_j2000_hours)}")
        st.markdown(f"Dec: {format_dec(obj.dec_j2000_degrees)}")
    with col_btn:
        if obj.above_horizon:
            if st.button("Slew", type="primary", key="slew_stellarium", use_container_width=True):
                _slew_and_report(alpaca, obj.ra_j2000_hours, obj.dec_j2000_degrees, obj.name)
        else:
            st.button(
                "Below horizon",
                disabled=True,
                key="slew_stellarium_disabled",
                use_container_width=True,
            )
            st.caption(f"Alt: {obj.altitude:.1f}")


def _render_object_search(alpaca, stellarium):
    """Named object search - Messier catalog first, then Stellarium fallback."""
    st.subheader("Object Search")
    st.caption(
        "Search the built-in Messier catalog first, then falls back to Stellarium's database."
    )
    col_search, col_btn = st.columns([4, 1])
    with col_search:
        query = st.text_input(
            "Search by name",
            placeholder="M42, Orion Nebula, NGC 7000...",
            key="object_search",
            help="Enter a Messier ID (M42), common name (Orion Nebula), "
            "or object type (galaxy, nebula). Searches the built-in "
            "Messier catalog, then Stellarium if available.",
        )
    with col_btn:
        st.write("")
        st.write("")
        do_search = st.button("Search", key="btn_search", use_container_width=True)

    if do_search and query:
        # Try Messier catalog first (exact lookup)
        messier_obj = lookup_messier(query)
        if messier_obj:
            st.success(
                f"Found: **{messier_obj['id']}** - {messier_obj['common_name']} "
                f"({messier_obj['object_type']})"
            )
            st.write(
                f"RA: {format_ra(messier_obj['ra_hours'])} | "
                f"Dec: {format_dec(messier_obj['dec_degrees'])}"
            )
            if st.button(f"Slew to {messier_obj['id']}", type="primary", key="slew_search_exact"):
                _slew_and_report(
                    alpaca,
                    messier_obj["ra_hours"],
                    messier_obj["dec_degrees"],
                    f"{messier_obj['id']} {messier_obj['common_name']}",
                )
            return

        # Try Messier catalog name search
        catalog_results = search_catalog(query)
        if catalog_results:
            st.info(f"Found {len(catalog_results)} catalog match(es):")
            for obj in catalog_results[:5]:
                col_obj, col_slew = st.columns([4, 1])
                with col_obj:
                    st.write(
                        f"**{obj['id']}** - {obj['common_name']} "
                        f"({obj['object_type']}) | "
                        f"RA {format_ra(obj['ra_hours'])} "
                        f"Dec {format_dec(obj['dec_degrees'])}"
                    )
                with col_slew:
                    if st.button("Slew", key=f"slew_cat_{obj['id']}"):
                        _slew_and_report(
                            alpaca,
                            obj["ra_hours"],
                            obj["dec_degrees"],
                            f"{obj['id']} {obj['common_name']}",
                        )
            return

        # Fallback to Stellarium lookup
        if stellarium.is_available():
            stel_obj = stellarium.lookup_object(query)
            if stel_obj:
                st.success(f"Found in Stellarium: **{stel_obj.name}** ({stel_obj.object_type})")
                st.write(
                    f"RA: {format_ra(stel_obj.ra_j2000_hours)} | "
                    f"Dec: {format_dec(stel_obj.dec_j2000_degrees)} | "
                    f"Alt: {stel_obj.altitude:.1f}"
                )
                if stel_obj.above_horizon:
                    if st.button(
                        f"Slew to {stel_obj.name}", type="primary", key="slew_search_stel"
                    ):
                        _slew_and_report(
                            alpaca,
                            stel_obj.ra_j2000_hours,
                            stel_obj.dec_j2000_degrees,
                            stel_obj.name,
                        )
                else:
                    st.warning(f"{stel_obj.name} is below the horizon")
                return

        st.warning(f"No object found matching '{query}'")


def _render_quick_targets(alpaca):
    """Quick-access buttons for popular deep sky objects."""
    st.subheader("Quick Targets")
    st.caption("Popular deep sky objects from the Messier catalog. Click to slew directly.")
    for row_start in range(0, len(QUICK_TARGETS), 4):
        cols = st.columns(4)
        for i, col in enumerate(cols):
            idx = row_start + i
            if idx >= len(QUICK_TARGETS):
                break
            mid, name = QUICK_TARGETS[idx]
            with col:
                if st.button(f"{mid}\n{name}", key=f"quick_{mid}", use_container_width=True):
                    obj = lookup_messier(mid)
                    if obj:
                        _slew_and_report(
                            alpaca, obj["ra_hours"], obj["dec_degrees"], f"{mid} {name}"
                        )


def _render_mount_controls(alpaca):
    """Open, Park, Stop, and Tracking controls."""
    st.subheader("Mount Controls")
    st.caption(
        "Open sends a slew to unfold the arm. Park attempts to close it "
        "(firmware-dependent). Tracking compensates for Earth's rotation."
    )
    alp_up = _check_alp_reachable()
    if not alp_up:
        st.warning(
            "Mount control unavailable — seestar-alp is not reachable at "
            f"{SEESTAR_ALP_URL}. Open / Park / Stop commands require this service."
        )
    col_open, col_park, col_stop, col_track = st.columns(4)
    with col_open:
        if st.button(
            "Open Scope",
            type="primary",
            use_container_width=True,
            disabled=not alp_up,
            help="Wake the Seestar into operational mode "
            "(iscope_start_view, mode=star) and unfold the arm. "
            "Required before any slew — the scope rejects movement "
            "commands while in HOME state with 'fail to operate'.",
        ):
            result = _seestar_action(
                "iscope_start_view",
                params={"params": {"mode": "star"}},
            )
            if not result["success"]:
                st.error(f"Open failed: {result['error']}")
            else:
                with st.spinner(f"Waiting for scope to open (up to {VERIFY_TIMEOUT_S}s)..."):
                    transitioned = _poll_state_transition(
                        alpaca,
                        lambda s: s.get("at_park", True) is False and s.get("at_home", True) is False,
                    )
                if transitioned:
                    st.success("Scope opened — arm is unfolded and ready.")
                    st.rerun()
                else:
                    st.error(
                        "Command sent but scope didn't leave HOME/park state. "
                        "It may be powered off, in HOME state with no power, or "
                        "firmware rejected the command. Check the Seestar app."
                    )
    with col_park:
        if st.button(
            "Park (Close)",
            use_container_width=True,
            disabled=not alp_up,
            help="Attempt to fold/close the telescope arm via scope_park. "
            "Note: may not work on all firmware versions. "
            "Use the Seestar app to park if this doesn't respond.",
        ):
            result = _seestar_action("scope_park")
            if not result["success"]:
                st.error(f"Park failed: {result['error']}")
            else:
                with st.spinner(f"Waiting for scope to park (up to {VERIFY_TIMEOUT_S}s)..."):
                    transitioned = _poll_state_transition(
                        alpaca,
                        lambda s: s.get("at_park", False) is True,
                    )
                if transitioned:
                    st.success("Scope parked — arm is closed.")
                    st.rerun()
                else:
                    st.error(
                        "Command sent but scope didn't reach park state. "
                        "Try the Seestar app to park manually."
                    )
    with col_stop:
        if st.button(
            "Stop Slew",
            use_container_width=True,
            disabled=not alp_up,
            help="Abort the current slew and stop the telescope. Uses the iscope_stop_view (AutoGoto) action.",
        ):
            result = _seestar_action("iscope_stop_view", params={"stage": "AutoGoto"})
            if not result["success"]:
                st.error(f"Stop failed: {result['error']}")
            else:
                with st.spinner(f"Waiting for slew to stop (up to {VERIFY_TIMEOUT_S}s)..."):
                    transitioned = _poll_state_transition(
                        alpaca,
                        lambda s: s.get("slewing", True) is False,
                    )
                if transitioned:
                    st.success("Scope is not slewing.")
                    st.rerun()
                else:
                    st.error(
                        "Command sent but scope is still reporting slewing=True. "
                        "Check the Seestar app."
                    )
    with col_track:
        try:
            status = alpaca.get_telescope_status()
            tracking = status.get("tracking", False)
        except Exception:
            tracking = False
        label = "Tracking OFF" if tracking else "Tracking ON"
        if st.button(
            label,
            use_container_width=True,
            help="Toggle sidereal tracking on/off. Tracking compensates "
            "for Earth's rotation to keep objects centered.",
        ):
            resp = alpaca.set_tracking(not tracking)
            if resp.success:
                st.success(f"Tracking {'enabled' if not tracking else 'disabled'}")
                st.rerun()
            else:
                st.error(f"Tracking toggle failed: {resp.error_message}")


def render_goto(alpaca, stellarium):
    """Render the GoTo/Slew control page."""
    st.header("\u2b50 GoTo / Slew Control")

    _render_current_position(alpaca)
    _render_slewing_progress(alpaca)

    st.divider()

    col_left, col_right = st.columns(2)
    with col_left:
        _render_manual_input(alpaca)
    with col_right:
        _render_stellarium_panel(alpaca, stellarium)

    st.divider()

    _render_object_search(alpaca, stellarium)

    st.divider()

    _render_quick_targets(alpaca)

    st.divider()

    _render_mount_controls(alpaca)
