"""GoTo/Slew control page with Stellarium integration and catalog search."""

import streamlit as st
import time

from utils.coordinates import format_ra, format_dec, parse_ra, parse_dec
from catalog.messier import lookup_messier, search_catalog


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
    # 4 columns x 3 rows = 12 targets
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
    """Park, Unpark, Home, and Tracking controls."""
    st.subheader("Mount Controls")
    st.caption(
        "Park stores the telescope safely. Unpark before slewing. Tracking compensates for Earth's rotation."
    )
    col_park, col_unpark, col_home, col_track = st.columns(4)
    with col_park:
        if st.button(
            "Park",
            use_container_width=True,
            help="Move the telescope to its safe park position. Always park before powering off.",
        ):
            resp = alpaca.park()
            if resp.success:
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"Park failed: {resp.error_message}")
    with col_unpark:
        if st.button(
            "Unpark",
            use_container_width=True,
            help="Release the telescope from park position so it can accept slew commands.",
        ):
            resp = alpaca.unpark()
            if resp.success:
                st.rerun()
            else:
                st.error(f"Unpark failed: {resp.error_message}")
    with col_home:
        if st.button(
            "Find Home",
            use_container_width=True,
            help="Slew to the home reference position. Useful for "
            "re-calibrating the mount's coordinate system.",
        ):
            resp = alpaca.find_home()
            if resp.success:
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"Find Home failed: {resp.error_message}")
    with col_track:
        try:
            status = alpaca.get_telescope_status()
            tracking = status.get("tracking", False)
        except Exception:
            tracking = False
        label = "Tracking OFF" if tracking else "Tracking ON"
        if st.button(label, use_container_width=True):
            resp = alpaca.set_tracking(not tracking)
            if resp.success:
                st.success(f"Tracking {'enabled' if not tracking else 'disabled'}")
                st.rerun()
            else:
                st.error(f"Tracking toggle failed: {resp.error_message}")


def render_goto(alpaca, stellarium):
    """Render the GoTo/Slew control page."""
    st.header("\u2b50 GoTo / Slew Control")

    # Current position at top
    _render_current_position(alpaca)

    # Slewing progress indicator
    _render_slewing_progress(alpaca)

    st.divider()

    # Two-column layout: Manual + Stellarium
    col_left, col_right = st.columns(2)
    with col_left:
        _render_manual_input(alpaca)
    with col_right:
        _render_stellarium_panel(alpaca, stellarium)

    st.divider()

    # Object search
    _render_object_search(alpaca, stellarium)

    st.divider()

    # Quick targets grid
    _render_quick_targets(alpaca)

    st.divider()

    # Mount controls
    _render_mount_controls(alpaca)
