"""Observation session logging to JSONL files."""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional


class SessionLogger:
    """Logs observation events to JSONL files in sessions/ directory."""

    def __init__(self, sessions_dir: str = "sessions"):
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.current_file = self.sessions_dir / f"session_{datetime.now().strftime('%Y%m%d')}.jsonl"

    def _write_event(self, event: str, **data):
        entry = {"event": event, "timestamp": datetime.now().isoformat(), **data}
        with open(self.current_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def log_session_start(self, location_lat: float = 0, location_long: float = 0):
        self._write_event("session_start", location_lat=location_lat, location_long=location_long)

    def log_target_slew(self, target_name: str, ra: float, dec: float):
        self._write_event("target_slew", target_name=target_name, ra=ra, dec=dec)

    def log_exposure_taken(self, target: str, exposure_s: float, gain: int, filter_name: str, filename: str):
        self._write_event("exposure_taken", target=target, exposure_s=exposure_s, gain=gain, filter_name=filter_name, filename=filename)

    def log_sequence_complete(self, targets: list, total_frames: int):
        self._write_event("sequence_complete", targets=targets, total_frames=total_frames)

    def log_session_end(self):
        self._write_event("session_end")

    def get_recent_sessions(self) -> list:
        return sorted([f.name for f in self.sessions_dir.glob("session_*.jsonl")], reverse=True)

    def get_session_summary(self, date_str: str) -> dict:
        filepath = self.sessions_dir / f"session_{date_str}.jsonl"
        if not filepath.exists():
            return {"error": "Session not found"}
        events = [json.loads(line) for line in filepath.read_text().strip().split("\n") if line.strip()]
        targets = list(set(e.get("target_name", e.get("target", "")) for e in events if e["event"] in ("target_slew", "exposure_taken") and (e.get("target_name") or e.get("target"))))
        exposures = [e for e in events if e["event"] == "exposure_taken"]
        return {"date": date_str, "total_events": len(events), "targets_observed": targets, "total_exposures": len(exposures)}
