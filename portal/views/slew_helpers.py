"""Slew-path helpers: state polling, park-aware preflight, error mapping.

These functions are shared by every slew entrypoint in goto.py (Quick Targets,
Search results, Manual coordinates, Stellarium target). Kept in their own module
so they can be unit-tested without spinning up Streamlit.
"""

import logging
import time
from typing import Callable, Tuple

logger = logging.getLogger(__name__)

# How long to wait for a state transition (park/unpark/slew) to be observed
# before giving up. Reads against the native ALPACA endpoint are ~50ms each;
# polling once per second is plenty.
DEFAULT_TRANSITION_TIMEOUT_S = 15

# ALPACA standard error number returned by the firmware when an operation is
# illegal in the current state (parked, below horizon, slewing, etc.). The
# associated ErrorMessage is just the action name, which is not informative.
ERR_INVALID_OPERATION = 1032


def poll_state_transition(
    alpaca,
    predicate: Callable[[dict], bool],
    timeout_s: int = DEFAULT_TRANSITION_TIMEOUT_S,
) -> bool:
    """Poll telescope state until predicate returns True or timeout_s elapses.

    Returns True if the transition was observed, False on timeout. Exceptions
    from get_telescope_status() are caught and retried; a False return
    therefore means either no transition or the scope became unreachable.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            status = alpaca.get_telescope_status()
            if predicate(status):
                return True
        except Exception as exc:
            logger.debug("poll_state_transition: status read failed: %s", exc)
        time.sleep(1)
    return False


def ensure_unparked(alpaca, timeout_s: int = 8) -> Tuple[bool, str]:
    """If the scope is parked, send Unpark and wait for AtPark to clear.

    Returns (ok, reason). ok=True means the scope is not parked and is ready
    to slew. ok=False means the scope is still parked because unpark was
    refused or AtPark didn't clear within timeout_s.
    """
    try:
        status = alpaca.get_telescope_status()
    except Exception as exc:
        return False, f"could not read park state: {exc}"

    if not status.get("at_park", False):
        return True, ""

    unpark_resp = alpaca.unpark()
    if not unpark_resp.success:
        return False, f"unpark refused: {unpark_resp.error_message}"

    cleared = poll_state_transition(
        alpaca,
        lambda s: s.get("at_park", True) is False,
        timeout_s=timeout_s,
    )
    if not cleared:
        return False, "unpark accepted but AtPark didn't clear in time"
    return True, ""


def format_slew_error(resp) -> str:
    """Map common ALPACA slew failures to a UX-friendly explanation."""
    if resp.error_number == ERR_INVALID_OPERATION:
        return (
            "scope refused the slew (firmware InvalidOperation). "
            "Common causes: still parked, target below horizon, or scope busy."
        )
    return resp.error_message or f"error {resp.error_number}"
