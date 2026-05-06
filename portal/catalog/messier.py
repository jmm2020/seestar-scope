"""Complete Messier catalog with all 110 objects.

J2000 coordinates. Format: (ra_hours, dec_degrees, common_name, object_type)
"""

import re
from typing import Optional

# Format: "M#": (ra_hours, dec_degrees, "Common Name", "Object Type")
MESSIER_CATALOG = {
    "M1":   (5.5753, 22.0145, "Crab Nebula", "Supernova Remnant"),
    "M2":   (21.5575, -0.8233, "M2", "Globular Cluster"),
    "M3":   (13.7033, 28.3772, "M3", "Globular Cluster"),
    "M4":   (16.3933, -26.5258, "M4", "Globular Cluster"),
    "M5":   (15.3092, 2.0828, "M5", "Globular Cluster"),
    "M6":   (17.6717, -32.2167, "Butterfly Cluster", "Open Cluster"),
    "M7":   (17.8983, -34.7933, "Ptolemy's Cluster", "Open Cluster"),
    "M8":   (18.0633, -24.3867, "Lagoon Nebula", "Diffuse Nebula"),
    "M9":   (17.3200, -18.5167, "M9", "Globular Cluster"),
    "M10":  (16.9525, -4.0997, "M10", "Globular Cluster"),
    "M11":  (18.8517, -6.2667, "Wild Duck Cluster", "Open Cluster"),
    "M12":  (16.7858, -1.9486, "M12", "Globular Cluster"),
    "M13":  (16.6948, 36.4613, "Great Globular Cluster", "Globular Cluster"),
    "M14":  (17.6258, -3.2458, "M14", "Globular Cluster"),
    "M15":  (21.4997, 12.1669, "M15", "Globular Cluster"),
    "M16":  (18.3133, -13.7833, "Eagle Nebula", "Diffuse Nebula"),
    "M17":  (18.3467, -16.1833, "Omega Nebula", "Diffuse Nebula"),
    "M18":  (18.3300, -17.1333, "M18", "Open Cluster"),
    "M19":  (17.0442, -26.2678, "M19", "Globular Cluster"),
    "M20":  (18.0433, -23.0333, "Trifid Nebula", "Diffuse Nebula"),
    "M21":  (18.0767, -22.4917, "M21", "Open Cluster"),
    "M22":  (18.6050, -23.9050, "M22", "Globular Cluster"),
    "M23":  (17.9483, -19.0167, "M23", "Open Cluster"),
    "M24":  (18.2833, -18.4833, "Sagittarius Star Cloud", "Star Cloud"),
    "M25":  (18.5267, -19.2333, "M25", "Open Cluster"),
    "M26":  (18.7517, -9.3833, "M26", "Open Cluster"),
    "M27":  (19.9939, 22.7211, "Dumbbell Nebula", "Planetary Nebula"),
    "M28":  (18.4092, -24.8700, "M28", "Globular Cluster"),
    "M29":  (20.3983, 38.5167, "M29", "Open Cluster"),
    "M30":  (21.6733, -23.1797, "M30", "Globular Cluster"),
    "M31":  (0.7123, 41.2689, "Andromeda Galaxy", "Galaxy"),
    "M32":  (0.7117, 40.8653, "M32", "Galaxy"),
    "M33":  (1.5642, 30.6602, "Triangulum Galaxy", "Galaxy"),
    "M34":  (2.7017, 42.7833, "M34", "Open Cluster"),
    "M35":  (6.1483, 24.3333, "M35", "Open Cluster"),
    "M36":  (5.6017, 34.1333, "M36", "Open Cluster"),
    "M37":  (5.8733, 32.5500, "M37", "Open Cluster"),
    "M38":  (5.4750, 35.8333, "M38", "Open Cluster"),
    "M39":  (21.5350, 48.4333, "M39", "Open Cluster"),
    "M40":  (12.3700, 58.0833, "Winnecke 4", "Double Star"),
    "M41":  (6.7833, -20.7333, "M41", "Open Cluster"),
    "M42":  (5.5881, -5.3911, "Orion Nebula", "Diffuse Nebula"),
    "M43":  (5.5933, -5.2667, "De Mairan's Nebula", "Diffuse Nebula"),
    "M44":  (8.6732, 19.6712, "Beehive Cluster", "Open Cluster"),
    "M45":  (3.7914, 24.1167, "Pleiades", "Open Cluster"),
    "M46":  (7.6967, -14.8167, "M46", "Open Cluster"),
    "M47":  (7.6100, -14.5000, "M47", "Open Cluster"),
    "M48":  (8.2267, -5.7500, "M48", "Open Cluster"),
    "M49":  (12.4967, 8.0003, "M49", "Galaxy"),
    "M50":  (7.0517, -8.3333, "M50", "Open Cluster"),
    "M51":  (13.4987, 47.1952, "Whirlpool Galaxy", "Galaxy"),
    "M52":  (23.4050, 61.5833, "M52", "Open Cluster"),
    "M53":  (13.2150, 18.1681, "M53", "Globular Cluster"),
    "M54":  (18.9175, -30.4786, "M54", "Globular Cluster"),
    "M55":  (19.6667, -30.9647, "M55", "Globular Cluster"),
    "M56":  (19.2767, 30.1842, "M56", "Globular Cluster"),
    "M57":  (18.8932, 33.0286, "Ring Nebula", "Planetary Nebula"),
    "M58":  (12.6283, 11.8181, "M58", "Galaxy"),
    "M59":  (12.7000, 11.6472, "M59", "Galaxy"),
    "M60":  (12.7283, 11.5525, "M60", "Galaxy"),
    "M61":  (12.3667, 4.4736, "M61", "Galaxy"),
    "M62":  (17.0233, -30.1133, "M62", "Globular Cluster"),
    "M63":  (13.2637, 42.0293, "Sunflower Galaxy", "Galaxy"),
    "M64":  (12.9467, 21.6828, "Black Eye Galaxy", "Galaxy"),
    "M65":  (11.3150, 13.0922, "M65", "Galaxy"),
    "M66":  (11.3367, 12.9914, "M66", "Galaxy"),
    "M67":  (8.8567, 11.8167, "M67", "Open Cluster"),
    "M68":  (12.6567, -26.7447, "M68", "Globular Cluster"),
    "M69":  (18.5233, -32.3481, "M69", "Globular Cluster"),
    "M70":  (18.7225, -32.2928, "M70", "Globular Cluster"),
    "M71":  (19.8967, 18.7792, "M71", "Globular Cluster"),
    "M72":  (20.8917, -12.5372, "M72", "Globular Cluster"),
    "M73":  (20.9817, -12.6333, "M73", "Asterism"),
    "M74":  (1.6117, 15.7833, "Phantom Galaxy", "Galaxy"),
    "M75":  (20.1008, -21.9214, "M75", "Globular Cluster"),
    "M76":  (1.7050, 51.5750, "Little Dumbbell Nebula", "Planetary Nebula"),
    "M77":  (2.7117, -0.0133, "Cetus A", "Galaxy"),
    "M78":  (5.7791, 0.0486, "M78 Nebula", "Diffuse Nebula"),
    "M79":  (5.4067, -24.5247, "M79", "Globular Cluster"),
    "M80":  (16.2833, -22.9758, "M80", "Globular Cluster"),
    "M81":  (9.9265, 69.0653, "Bode's Galaxy", "Galaxy"),
    "M82":  (9.9318, 69.6797, "Cigar Galaxy", "Galaxy"),
    "M83":  (13.6167, -29.8658, "Southern Pinwheel Galaxy", "Galaxy"),
    "M84":  (12.4183, 12.8872, "M84", "Galaxy"),
    "M85":  (12.4217, 18.1911, "M85", "Galaxy"),
    "M86":  (12.4367, 12.9467, "M86", "Galaxy"),
    "M87":  (12.5133, 12.3911, "Virgo A", "Galaxy"),
    "M88":  (12.5317, 14.4203, "M88", "Galaxy"),
    "M89":  (12.5933, 12.5564, "M89", "Galaxy"),
    "M90":  (12.6133, 13.1628, "M90", "Galaxy"),
    "M91":  (12.5917, 14.4964, "M91", "Galaxy"),
    "M92":  (17.2858, 43.1364, "M92", "Globular Cluster"),
    "M93":  (7.7433, -23.8500, "M93", "Open Cluster"),
    "M94":  (12.8517, 41.1203, "Cat's Eye Galaxy", "Galaxy"),
    "M95":  (10.7333, 11.7039, "M95", "Galaxy"),
    "M96":  (10.7833, 11.8194, "M96", "Galaxy"),
    "M97":  (11.2467, 55.0194, "Owl Nebula", "Planetary Nebula"),
    "M98":  (12.2267, 14.9003, "M98", "Galaxy"),
    "M99":  (12.3133, 14.4164, "Coma Pinwheel Galaxy", "Galaxy"),
    "M100": (12.3833, 15.8228, "M100", "Galaxy"),
    "M101": (14.0533, 54.3489, "Pinwheel Galaxy", "Galaxy"),
    "M102": (15.1083, 55.7633, "Spindle Galaxy", "Galaxy"),
    "M103": (1.5550, 60.7000, "M103", "Open Cluster"),
    "M104": (12.6662, -11.6231, "Sombrero Galaxy", "Galaxy"),
    "M105": (10.7967, 12.5817, "M105", "Galaxy"),
    "M106": (12.3167, 47.3039, "M106", "Galaxy"),
    "M107": (16.5417, -13.0536, "M107", "Globular Cluster"),
    "M108": (11.1933, 55.6739, "Surfboard Galaxy", "Galaxy"),
    "M109": (11.9600, 53.3744, "M109", "Galaxy"),
    "M110": (0.6733, 41.6856, "M110", "Galaxy"),
}


def _normalize_messier_id(name: str) -> Optional[str]:
    """Normalize various Messier ID formats to 'M##'."""
    name = name.strip().upper().replace(" ", "")
    match = re.match(r"^M(\d{1,3})$", name)
    if match:
        return f"M{int(match.group(1))}"
    return None


def _entry_to_dict(messier_id: str, entry: tuple) -> dict:
    """Convert a catalog tuple to a dict."""
    ra_hours, dec_deg, common_name, obj_type = entry
    return {
        "id": messier_id,
        "ra_hours": ra_hours,
        "dec_degrees": dec_deg,
        "common_name": common_name,
        "object_type": obj_type,
    }


def lookup_messier(name: str) -> Optional[dict]:
    """Look up a Messier object by ID.

    Accepts formats: "M42", "m42", "M 42", "m 42".
    Returns dict with id, ra_hours, dec_degrees, common_name, object_type
    or None if not found.
    """
    mid = _normalize_messier_id(name)
    if mid and mid in MESSIER_CATALOG:
        return _entry_to_dict(mid, MESSIER_CATALOG[mid])
    return None


def search_catalog(query: str) -> list[dict]:
    """Search the Messier catalog by common name or object type.

    Case-insensitive substring match. E.g., "Orion" finds "Orion Nebula" (M42).
    Also matches Messier IDs like "M42".
    """
    query_lower = query.strip().lower()
    results = []
    for mid, entry in MESSIER_CATALOG.items():
        ra_hours, dec_deg, common_name, obj_type = entry
        if (query_lower in mid.lower()
                or query_lower in common_name.lower()
                or query_lower in obj_type.lower()):
            results.append(_entry_to_dict(mid, entry))
    return results


def get_all_objects() -> list[dict]:
    """Return all 110 Messier objects as a list of dicts."""
    return [_entry_to_dict(mid, entry) for mid, entry in MESSIER_CATALOG.items()]


def get_objects_by_type(obj_type: str) -> list[dict]:
    """Filter Messier objects by type.

    Case-insensitive substring match. E.g., "galaxy" returns all galaxies,
    "globular" returns all globular clusters.
    """
    obj_type_lower = obj_type.strip().lower()
    return [
        _entry_to_dict(mid, entry)
        for mid, entry in MESSIER_CATALOG.items()
        if obj_type_lower in entry[3].lower()
    ]
