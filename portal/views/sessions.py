"""Sessions history view — timeline of past observation sessions with frame detail."""
from datetime import datetime
from typing import List, Optional

import streamlit as st

from clients.sessions_client import SessionsClient


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _session_duration_minutes(session: dict) -> Optional[float]:
    started = _parse_dt(session.get("started_at"))
    ended = _parse_dt(session.get("ended_at"))
    if started is None or ended is None:
        return None
    return (ended - started).total_seconds() / 60.0


def _render_session_stats(sessions: List[dict], frames_by_session: dict):
    """Summary metrics computed client-side from the list response."""
    total_sessions = len(sessions)
    total_frames = sum(len(frames_by_session.get(s["id"], [])) for s in sessions)
    total_exposure_s = sum(
        f.get("exposure_s", 0.0)
        for s in sessions
        for f in frames_by_session.get(s["id"], [])
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Sessions", total_sessions)
    c2.metric("Frames", total_frames)
    c3.metric("Total Exposure", f"{total_exposure_s / 3600.0:.2f} h")


def _render_session_list(sessions: List[dict], frames_by_session: dict):
    """Table-style timeline of past sessions."""
    if not sessions:
        st.info("No sessions yet — start a stack or run a sequence to record one.")
        return

    header = st.columns([2, 2, 1, 1.2, 1.2, 1, 1])
    header[0].markdown("**Target**")
    header[1].markdown("**Started**")
    header[2].markdown("**Frames**")
    header[3].markdown("**Exposure**")
    header[4].markdown("**Duration**")
    header[5].markdown("**Status**")
    header[6].markdown("**Action**")

    for s in sessions:
        sid = s["id"]
        frames = frames_by_session.get(sid, [])
        frame_count = len(frames)
        total_exp = sum(f.get("exposure_s", 0.0) for f in frames)
        duration_min = _session_duration_minutes(s)
        ended = s.get("ended_at") is not None
        started_dt = _parse_dt(s.get("started_at"))

        cols = st.columns([2, 2, 1, 1.2, 1.2, 1, 1])
        cols[0].text(s.get("target_name", "?"))
        cols[1].text(started_dt.strftime("%Y-%m-%d %H:%M") if started_dt else "—")
        cols[2].text(str(frame_count))
        cols[3].text(f"{total_exp:.0f}s" if total_exp else "—")
        cols[4].text(f"{duration_min:.1f}m" if duration_min is not None else "—")
        cols[5].text("ended" if ended else "active")
        if cols[6].button("View", key=f"sess_view_{sid}"):
            st.session_state["selected_session_id"] = sid
            st.rerun()


def _render_session_detail(session_id: int, client: SessionsClient):
    """Detail panel for a single session: metadata, frames, re-open action."""
    session = client.get_session(session_id)
    if session is None:
        st.error(f"Could not load session {session_id} — backend unreachable")
        return

    st.subheader(f"Session #{session_id}: {session.get('target_name', '?')}")

    started_dt = _parse_dt(session.get("started_at"))
    duration_min = _session_duration_minutes(session)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("RA (h)", f"{session['target_ra']:.3f}" if session.get("target_ra") is not None else "—")
    c2.metric("Dec (°)", f"{session['target_dec']:.2f}" if session.get("target_dec") is not None else "—")
    c3.metric("Started", started_dt.strftime("%Y-%m-%d %H:%M") if started_dt else "—")
    c4.metric("Duration", f"{duration_min:.1f}m" if duration_min is not None else "active")

    if session.get("conditions_snapshot"):
        with st.expander("Conditions"):
            st.json(session["conditions_snapshot"])

    frames = client.get_frames(session_id) or []
    st.markdown(f"**{len(frames)} frames**")

    if frames:
        rows = [
            {
                "filename": f.get("filename", "?"),
                "exposure_s": f.get("exposure_s"),
                "gain": f.get("gain"),
                "filter": f.get("filter"),
                "captured_at": f.get("captured_at"),
            }
            for f in frames
        ]
        st.dataframe(rows, use_container_width=True)

    col_back, col_reopen = st.columns([1, 1])
    if col_back.button("Back to list", key="sess_detail_back"):
        st.session_state.pop("selected_session_id", None)
        st.rerun()
    if col_reopen.button("Re-open Session", key="sess_detail_reopen", type="primary"):
        st.session_state["slewing_target"] = session.get("target_name")
        if session.get("target_ra") is not None:
            st.session_state["reopen_ra"] = session["target_ra"]
        if session.get("target_dec") is not None:
            st.session_state["reopen_dec"] = session["target_dec"]
        st.success(
            f"Loaded {session.get('target_name')} into session state — "
            "switch to Imaging or GoTo to use it."
        )


def render_sessions():
    """Main entry point — called from app.py routing."""
    st.header("\U0001f4cb Session History")

    client = SessionsClient()
    selected_id = st.session_state.get("selected_session_id")

    if selected_id is not None:
        _render_session_detail(int(selected_id), client)
        return

    sessions = client.list_sessions()
    if sessions is None:
        st.error("Session history unavailable — backend not running")
        return

    frames_by_session = {}
    for s in sessions:
        frames = client.get_frames(s["id"]) or []
        frames_by_session[s["id"]] = frames

    _render_session_stats(sessions, frames_by_session)
    st.divider()
    _render_session_list(sessions, frames_by_session)
