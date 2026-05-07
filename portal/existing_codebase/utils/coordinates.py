"""RA/Dec coordinate parsing, conversion, and formatting utilities."""
import re


def ra_degrees_to_hours(deg: float) -> float:
    """Convert RA from degrees to hours.

    Stellarium returns RA in degrees (raJ2000). ALPACA expects RA in hours.
    If the value is negative, add 360 before dividing by 15.
    """
    if deg < 0:
        deg += 360
    return deg / 15.0


def ra_hours_to_degrees(hours: float) -> float:
    """Convert RA from hours to degrees."""
    return hours * 15.0


def hours_to_hms(hours: float) -> tuple[int, int, float]:
    """Split decimal hours into (hours, minutes, seconds) components."""
    h = int(hours)
    remainder = (hours - h) * 60
    m = int(remainder)
    s = (remainder - m) * 60
    return h, m, round(s, 1)


def degrees_to_dms(deg: float) -> tuple[int, int, float, str]:
    """Split decimal degrees into (degrees, arcminutes, arcseconds, sign) components."""
    sign = "+" if deg >= 0 else "-"
    deg = abs(deg)
    d = int(deg)
    remainder = (deg - d) * 60
    m = int(remainder)
    s = (remainder - m) * 60
    return d, m, round(s, 1), sign


def format_ra(hours: float) -> str:
    """Format RA as 'Hh Mm S.Ss' (e.g., 7.620278 -> '7h 37m 13.0s')."""
    h, m, s = hours_to_hms(hours)
    return f"{h}h {m:02d}m {s:04.1f}s"


def format_dec(deg: float) -> str:
    """Format Dec as '+/-DD deg MM' SS.S\"' (e.g., -23.76 -> '-23 deg 45' 36.0\"')."""
    d, m, s, sign = degrees_to_dms(deg)
    return f"{sign}{d}\u00b0 {m:02d}' {s:04.1f}\""


def parse_ra(text: str) -> float:
    """Parse RA from string to decimal hours.

    Accepts:
    - 'HH:MM:SS' or 'HH:MM:SS.S'
    - 'HHh MMm SSs' or 'HHh MMm SS.Ss'
    - Plain decimal hours (e.g., '5.588')
    """
    text = text.strip()

    # Try HHh MMm SSs format
    match = re.match(r"(\d+)h\s*(\d+)m\s*([\d.]+)s?", text, re.IGNORECASE)
    if match:
        h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
        return h + m / 60.0 + s / 3600.0

    # Try HH:MM:SS format
    match = re.match(r"(\d+):(\d+):([\d.]+)", text)
    if match:
        h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
        return h + m / 60.0 + s / 3600.0

    # Try plain decimal
    return float(text)


def parse_dec(text: str) -> float:
    """Parse Dec from string to decimal degrees.

    Accepts:
    - 'DD:MM:SS' or '+/-DD:MM:SS.S'
    - '+/-DD deg MM' SS\"' or '+/-DD deg MM' SS.S\"'
    - Plain decimal degrees (e.g., '-23.76')
    """
    text = text.strip()

    # Try +/-DD deg MM' SS" format
    match = re.match(r"([+-]?)(\d+)\u00b0\s*(\d+)['']\s*([\d.]+)[\"\"]?", text)
    if match:
        sign = -1 if match.group(1) == "-" else 1
        d, m, s = int(match.group(2)), int(match.group(3)), float(match.group(4))
        return sign * (d + m / 60.0 + s / 3600.0)

    # Try +/-DD:MM:SS format
    match = re.match(r"([+-]?)(\d+):(\d+):([\d.]+)", text)
    if match:
        sign = -1 if match.group(1) == "-" else 1
        d, m, s = int(match.group(2)), int(match.group(3)), float(match.group(4))
        return sign * (d + m / 60.0 + s / 3600.0)

    # Try plain decimal
    return float(text)
