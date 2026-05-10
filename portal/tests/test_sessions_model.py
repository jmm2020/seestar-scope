"""Tests for SessionDatabase - in-memory SQLite, no live backend required."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.sessions import SessionDatabase


def _db():
    return SessionDatabase(db_path=":memory:")


def test_create_session_returns_id():
    db = _db()
    sid = db.create_session(target_name="M31", target_ra=0.712, target_dec=41.27)
    assert isinstance(sid, int)
    assert sid > 0


def test_get_by_id_returns_record():
    db = _db()
    sid = db.create_session(target_name="M42", target_ra=5.588, target_dec=-5.39)
    record = db.get_by_id(sid)
    assert record is not None
    assert record.target_name == "M42"
    assert record.target_ra == 5.588
    assert record.target_dec == -5.39
    assert record.ended_at is None
    assert isinstance(record.started_at, datetime)


def test_get_by_id_missing_returns_none():
    db = _db()
    assert db.get_by_id(999) is None


def test_end_session_sets_ended_at():
    db = _db()
    sid = db.create_session(target_name="NGC7000")
    assert db.end_session(sid) is True
    record = db.get_by_id(sid)
    assert record.ended_at is not None
    assert isinstance(record.ended_at, datetime)


def test_end_session_idempotent():
    db = _db()
    sid = db.create_session(target_name="X")
    db.end_session(sid)
    first_ended = db.get_by_id(sid).ended_at
    # Second end call overwrites ended_at
    db.end_session(sid)
    second_ended = db.get_by_id(sid).ended_at
    assert second_ended >= first_ended


def test_end_session_missing_returns_false():
    db = _db()
    assert db.end_session(999) is False


def test_add_frame_returns_id_and_increments():
    db = _db()
    sid = db.create_session(target_name="M31")
    fid1 = db.add_frame(sid, "f1.fits", 10.0, 80, "L")
    fid2 = db.add_frame(sid, "f2.fits", 10.0, 80, "L")
    assert fid2 == fid1 + 1


def test_get_frames_returns_in_order():
    db = _db()
    sid = db.create_session(target_name="M31")
    db.add_frame(sid, "f1.fits", 10.0, 80, "L")
    db.add_frame(sid, "f2.fits", 10.0, 80, "Ha")
    frames = db.get_frames(sid)
    assert len(frames) == 2
    assert frames[0].filename == "f1.fits"
    assert frames[1].filter == "Ha"


def test_list_sessions_empty():
    db = _db()
    assert db.list_sessions() == []


def test_list_sessions_newest_first():
    db = _db()
    db.create_session(target_name="A")
    db.create_session(target_name="B")
    sessions = db.list_sessions()
    assert len(sessions) == 2
    # Newest first
    assert sessions[0].started_at >= sessions[1].started_at


def test_session_with_json_fields():
    db = _db()
    sid = db.create_session(
        target_name="M31",
        site_location={"lat": 42.0, "lon": -71.0, "elevation": 100.0},
        conditions_snapshot={"seeing": 2.5, "transparency": "good"},
    )
    record = db.get_by_id(sid)
    assert record.site_location["lat"] == 42.0
    assert record.conditions_snapshot["seeing"] == 2.5


def test_add_stack_returns_id():
    db = _db()
    sid = db.create_session(target_name="M31")
    stack_id = db.add_stack(
        session_id=sid,
        output_path="/out/stack.fits",
        frame_count=10,
        algorithm="mean",
    )
    assert isinstance(stack_id, int)
    stacks = db.get_stacks(sid)
    assert len(stacks) == 1
    assert stacks[0].frame_count == 10


def test_end_session_updates_conditions_snapshot():
    db = _db()
    sid = db.create_session(target_name="M31")
    db.end_session(sid, conditions_snapshot={"seeing": 3.0, "transparency": "excellent"})
    record = db.get_by_id(sid)
    assert record.ended_at is not None
    assert record.conditions_snapshot["seeing"] == 3.0
    assert record.conditions_snapshot["transparency"] == "excellent"


def test_get_session_summaries_returns_counts():
    db = _db()
    sid1 = db.create_session(target_name="M31")
    sid2 = db.create_session(target_name="M42")
    db.add_frame(sid1, "f1.fits", 10.0, 80, "L")
    db.add_frame(sid1, "f2.fits", 20.0, 80, "Ha")
    db.add_frame(sid2, "f3.fits", 5.0, 80, "L")
    summaries = db.get_session_summaries([sid1, sid2])
    assert summaries[sid1]["frame_count"] == 2
    assert summaries[sid1]["total_exposure_s"] == 30.0
    assert summaries[sid2]["frame_count"] == 1
    assert summaries[sid2]["total_exposure_s"] == 5.0


def test_get_session_summaries_empty_list():
    db = _db()
    assert db.get_session_summaries([]) == {}
