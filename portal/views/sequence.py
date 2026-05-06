"""Imaging sequence builder - multi-target automated capture runs."""
import json
import time
from pathlib import Path

import streamlit as st

from catalog.messier import lookup_messier, search_catalog


FILTER_OPTIONS = ["Dark", "IR", "LP"]


def _init_sequence_state():
    """Initialize session state for sequence builder."""
    if "sequence_targets" not in st.session_state:
        st.session_state.sequence_targets = []
    if "sequence_running" not in st.session_state:
        st.session_state.sequence_running = False
    if "sequence_current_idx" not in st.session_state:
        st.session_state.sequence_current_idx = 0
    if "sequence_current_frame" not in st.session_state:
        st.session_state.sequence_current_frame = 0


def _render_add_target(stellarium):
    """Controls for adding targets to the sequence."""
    st.subheader("Add Target")
    st.caption("Build a multi-target imaging plan. Each target gets its own exposure, gain, and filter settings.")

    tab_manual, tab_catalog, tab_stellarium = st.tabs(
        ["Manual Entry", "Catalog Lookup", "From Stellarium"]
    )

    with tab_manual:
        col_name, col_ra, col_dec = st.columns(3)
        with col_name:
            name = st.text_input("Target Name", key="seq_manual_name",
                                help="A descriptive name for the target (used in filenames).")
        with col_ra:
            ra = st.number_input("RA (hours)", min_value=0.0, max_value=24.0,
                                 value=0.0, step=0.1, key="seq_manual_ra",
                                 help="Right Ascension in decimal hours (0-24). "
                                      "Example: M42 = 5.588h")
        with col_dec:
            dec = st.number_input("Dec (degrees)", min_value=-90.0, max_value=90.0,
                                  value=0.0, step=0.1, key="seq_manual_dec",
                                  help="Declination in decimal degrees (-90 to +90). "
                                       "Example: M42 = -5.39\u00b0")

        col_exp, col_gain, col_filt, col_frames = st.columns(4)
        with col_exp:
            exposure = st.number_input("Exposure (s)", min_value=0.001,
                                       max_value=2000.0, value=10.0, step=1.0,
                                       key="seq_manual_exp",
                                       help="Exposure time per frame in seconds.")
        with col_gain:
            gain = st.number_input("Gain", min_value=0, max_value=400,
                                   value=80, step=10, key="seq_manual_gain",
                                   help="Sensor gain for this target (0-400).")
        with col_filt:
            filt = st.selectbox("Filter", FILTER_OPTIONS, key="seq_manual_filter",
                                help="Dark = no filter, IR = infrared cut, LP = light pollution.")
        with col_frames:
            frames = st.number_input("Frames", min_value=1, max_value=999,
                                     value=10, step=1, key="seq_manual_frames",
                                     help="Number of exposures to capture for this target. "
                                          "More frames = better signal when stacked.")

        if st.button("Add Manual Target", key="seq_add_manual"):
            if name:
                st.session_state.sequence_targets.append({
                    "name": name, "ra": ra, "dec": dec,
                    "exposure": exposure, "gain": gain,
                    "filter": filt, "filter_idx": FILTER_OPTIONS.index(filt),
                    "frames": frames,
                })
                st.rerun()
            else:
                st.warning("Enter a target name")

    with tab_catalog:
        query = st.text_input("Search Messier catalog", key="seq_catalog_query",
                              placeholder="M42, Orion, Galaxy...")
        if query:
            # Try direct lookup first
            result = lookup_messier(query)
            if result:
                results = [result]
            else:
                results = search_catalog(query)

            if results:
                for r in results[:10]:
                    label = f"{r['id']} - {r['common_name']} ({r['object_type']})"
                    col_info, col_add = st.columns([4, 1])
                    with col_info:
                        st.text(f"{label}  RA: {r['ra_hours']:.3f}h  Dec: {r['dec_degrees']:.2f}")
                    with col_add:
                        if st.button("Add", key=f"seq_cat_{r['id']}"):
                            st.session_state.sequence_targets.append({
                                "name": f"{r['id']} {r['common_name']}",
                                "ra": r["ra_hours"],
                                "dec": r["dec_degrees"],
                                "exposure": 10.0, "gain": 80,
                                "filter": "LP", "filter_idx": 2,
                                "frames": 10,
                            })
                            st.rerun()
            else:
                st.info("No matches found")

    with tab_stellarium:
        if st.button("Get Stellarium Selection", key="seq_get_stellarium"):
            obj = stellarium.get_selected_object()
            if obj:
                st.session_state["seq_stell_obj"] = obj
            else:
                st.warning("No object selected in Stellarium")

        obj = st.session_state.get("seq_stell_obj")
        if obj:
            st.success(f"**{obj.name}** ({obj.object_type}) - "
                       f"RA: {obj.ra_j2000_hours:.4f}h  Dec: {obj.dec_j2000_degrees:.4f}")
            if obj.above_horizon:
                if st.button("Add to Sequence", key="seq_add_stellarium"):
                    st.session_state.sequence_targets.append({
                        "name": obj.name,
                        "ra": obj.ra_j2000_hours,
                        "dec": obj.dec_j2000_degrees,
                        "exposure": 10.0, "gain": 80,
                        "filter": "LP", "filter_idx": 2,
                        "frames": 10,
                    })
                    st.session_state.pop("seq_stell_obj", None)
                    st.rerun()
            else:
                st.warning(f"{obj.name} is below the horizon")


def _render_sequence_list():
    """Display and edit the current sequence target list."""
    st.subheader("Sequence Targets")
    targets = st.session_state.sequence_targets

    if not targets:
        st.info("No targets added. Use the controls above to add targets.")
        return

    for i, t in enumerate(targets):
        with st.container():
            cols = st.columns([3, 1.5, 1.5, 1, 1, 1, 1, 0.5])
            with cols[0]:
                st.text(f"{i+1}. {t['name']}")
            with cols[1]:
                st.text(f"RA: {t['ra']:.3f}h")
            with cols[2]:
                st.text(f"Dec: {t['dec']:.2f}")
            with cols[3]:
                st.text(f"{t['exposure']}s")
            with cols[4]:
                st.text(f"G{t['gain']}")
            with cols[5]:
                st.text(t["filter"])
            with cols[6]:
                st.text(f"x{t['frames']}")
            with cols[7]:
                if st.button("X", key=f"seq_rm_{i}",
                             disabled=st.session_state.sequence_running):
                    st.session_state.sequence_targets.pop(i)
                    st.rerun()

    total_frames = sum(t["frames"] for t in targets)
    total_time = sum(t["frames"] * t["exposure"] for t in targets)
    st.caption(f"**{len(targets)} targets** | {total_frames} total frames | "
               f"~{total_time:.0f}s exposure time (excluding slew/readout)")


def _render_run_controls(alpaca):
    """Run, stop, and progress display for sequence execution."""
    targets = st.session_state.sequence_targets
    if not targets:
        return

    st.divider()

    col_run, col_stop, col_save, col_load = st.columns(4)

    with col_run:
        if st.button("Run Sequence", type="primary", use_container_width=True,
                      key="seq_run",
                      disabled=st.session_state.sequence_running or not targets,
                      help="Start executing all targets in order: slew, configure, "
                           "capture frames, then advance to the next target."):
            st.session_state.sequence_running = True
            st.session_state.sequence_current_idx = 0
            st.session_state.sequence_current_frame = 0
            st.rerun()

    with col_stop:
        if st.button("Stop", use_container_width=True, key="seq_stop",
                      disabled=not st.session_state.sequence_running,
                      help="Abort the running sequence and stop the current exposure."):
            st.session_state.sequence_running = False
            alpaca.abort_exposure()
            st.warning("Sequence stopped")

    with col_save:
        if st.button("Save Sequence", use_container_width=True, key="seq_save",
                      help="Save the current target list to a JSON file "
                           "for reuse in future sessions."):
            _save_sequence(targets)

    with col_load:
        if st.button("Load Sequence", use_container_width=True, key="seq_load",
                      help="Load a previously saved sequence from disk."):
            st.session_state["show_load_dialog"] = True

    # Load file picker
    if st.session_state.get("show_load_dialog"):
        _render_load_dialog()

    # Sequence execution loop
    if st.session_state.sequence_running:
        _execute_sequence_step(alpaca)


def _execute_sequence_step(alpaca):
    """Execute one step of the sequence (non-blocking via st.rerun)."""
    targets = st.session_state.sequence_targets
    idx = st.session_state.sequence_current_idx
    frame = st.session_state.sequence_current_frame

    if idx >= len(targets):
        st.session_state.sequence_running = False
        st.success("Sequence complete!")
        st.balloons()
        return

    target = targets[idx]

    # Progress display
    total_frames = sum(t["frames"] for t in targets)
    completed_frames = sum(t["frames"] for t in targets[:idx]) + frame
    st.progress(completed_frames / max(total_frames, 1),
                text=f"Target {idx+1}/{len(targets)}: {target['name']} - "
                     f"Frame {frame+1}/{target['frames']}")

    # State machine for current target
    step = st.session_state.get("seq_step", "slew")

    if step == "slew":
        st.info(f"Slewing to {target['name']}...")
        resp = alpaca.slew_to(target["ra"], target["dec"])
        if resp.success:
            st.session_state["seq_step"] = "wait_slew"
            time.sleep(1)
            st.rerun()
        else:
            st.error(f"Slew failed: {resp.error_message}")
            st.session_state.sequence_running = False

    elif step == "wait_slew":
        status = alpaca.get_telescope_status()
        if status.get("slewing"):
            st.info(f"Slewing to {target['name']}...")
            time.sleep(2)
            st.rerun()
        else:
            st.session_state["seq_step"] = "configure"
            st.rerun()

    elif step == "configure":
        st.info(f"Configuring: gain={target['gain']}, filter={target['filter']}")
        alpaca.set_gain(target["gain"])
        alpaca.set_filter(target["filter_idx"])
        time.sleep(0.5)
        st.session_state["seq_step"] = "expose"
        st.rerun()

    elif step == "expose":
        st.info(f"Exposing frame {frame+1}/{target['frames']} - "
                f"{target['exposure']}s")
        resp = alpaca.start_exposure(target["exposure"], light=True)
        if resp.success:
            st.session_state["seq_step"] = "wait_expose"
            time.sleep(1)
            st.rerun()
        else:
            st.error(f"Exposure failed: {resp.error_message}")
            st.session_state.sequence_running = False

    elif step == "wait_expose":
        if alpaca.is_image_ready():
            # Frame done, advance
            st.session_state.sequence_current_frame = frame + 1
            if frame + 1 >= target["frames"]:
                # Target complete, advance to next
                st.session_state.sequence_current_idx = idx + 1
                st.session_state.sequence_current_frame = 0
                st.session_state["seq_step"] = "slew"
            else:
                st.session_state["seq_step"] = "expose"
            st.rerun()
        else:
            cam = alpaca.get_camera_status()
            st.info(f"Camera: {cam.get('state', 'working')} - "
                    f"frame {frame+1}/{target['frames']}")
            time.sleep(2)
            st.rerun()


def _save_sequence(targets):
    """Save sequence to a JSON file."""
    path = Path("sessions")
    path.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    filename = path / f"sequence_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w") as f:
        json.dump(targets, f, indent=2)
    st.success(f"Saved: {filename}")


def _render_load_dialog():
    """Show saved sequence files for loading."""
    path = Path("sessions")
    files = sorted(path.glob("sequence_*.json"), reverse=True) if path.exists() else []

    if not files:
        st.info("No saved sequences found")
        st.session_state["show_load_dialog"] = False
        return

    selected = st.selectbox("Select sequence file",
                            [f.name for f in files],
                            key="seq_load_file")
    if st.button("Load Selected", key="seq_do_load"):
        filepath = path / selected
        with open(filepath) as f:
            st.session_state.sequence_targets = json.load(f)
        st.session_state["show_load_dialog"] = False
        st.rerun()

    if st.button("Cancel", key="seq_load_cancel"):
        st.session_state["show_load_dialog"] = False
        st.rerun()


def render_sequence(alpaca, stellarium):
    """Render the imaging sequence builder page."""
    st.header("\U0001f3ac Imaging Sequence Builder")
    _init_sequence_state()
    _render_add_target(stellarium)
    st.divider()
    _render_sequence_list()
    _render_run_controls(alpaca)
