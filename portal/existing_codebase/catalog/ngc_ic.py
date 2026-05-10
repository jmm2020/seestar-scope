"""Extended NGC and IC catalog for Seestar S50.

Popular deep-sky objects with J2000 coordinates.
Format: (ra_hours, dec_degrees, common_name, object_type)
"""

import re
from typing import Optional

# ~50 popular NGC objects suitable for Seestar S50
NGC_CATALOG = {
    "NGC224": (0.7123, 41.2689, "Andromeda Galaxy", "Galaxy"),  # = M31
    "NGC253": (0.7925, -25.2883, "Sculptor Galaxy", "Galaxy"),
    "NGC281": (0.8775, 56.6267, "Pacman Nebula", "Emission Nebula"),
    "NGC457": (1.3267, 58.2833, "Owl Cluster", "Open Cluster"),
    "NGC663": (1.7733, 61.2333, "NGC 663", "Open Cluster"),
    "NGC752": (1.9617, 37.7833, "NGC 752", "Open Cluster"),
    "NGC869": (2.3200, 57.1333, "Double Cluster h Per", "Open Cluster"),
    "NGC884": (2.3733, 57.1500, "Double Cluster chi Per", "Open Cluster"),
    "NGC891": (2.3772, 42.3492, "Silver Sliver Galaxy", "Galaxy"),
    "NGC1023": (2.6733, 39.0633, "NGC 1023", "Galaxy"),
    "NGC1333": (3.4858, 31.3550, "NGC 1333", "Reflection Nebula"),
    "NGC1491": (4.0542, 51.3133, "Fossil Footprint Nebula", "Emission Nebula"),
    "NGC1499": (4.0517, 36.3833, "California Nebula", "Emission Nebula"),
    "NGC1502": (4.0783, 62.3333, "NGC 1502", "Open Cluster"),
    "NGC1528": (4.2550, 51.2167, "NGC 1528", "Open Cluster"),
    "NGC1977": (5.5850, -4.8383, "Running Man Nebula", "Reflection Nebula"),
    "NGC2024": (5.6850, -1.8500, "Flame Nebula", "Emission Nebula"),
    "NGC2070": (5.6458, -69.1000, "Tarantula Nebula", "Emission Nebula"),
    "NGC2174": (6.1650, 20.4917, "Monkey Head Nebula", "Emission Nebula"),
    "NGC2237": (6.5317, 5.0500, "Rosette Nebula", "Emission Nebula"),
    "NGC2244": (6.5317, 4.9500, "Rosette Cluster", "Open Cluster"),
    "NGC2264": (6.6833, 9.8950, "Cone Nebula / Christmas Tree", "Emission Nebula"),
    "NGC2359": (7.3067, -13.2333, "Thor's Helmet", "Emission Nebula"),
    "NGC2392": (7.4867, 20.9117, "Eskimo Nebula", "Planetary Nebula"),
    "NGC2403": (7.6150, 65.6025, "NGC 2403", "Galaxy"),
    "NGC2841": (9.3550, 50.9764, "Tiger's Eye Galaxy", "Galaxy"),
    "NGC2903": (9.5408, 21.5011, "NGC 2903", "Galaxy"),
    "NGC3242": (10.4117, -18.6381, "Ghost of Jupiter", "Planetary Nebula"),
    "NGC3372": (10.7500, -59.8667, "Carina Nebula", "Emission Nebula"),
    "NGC3628": (11.3383, 13.5883, "Hamburger Galaxy", "Galaxy"),
    "NGC4244": (12.2925, 37.8072, "Silver Needle Galaxy", "Galaxy"),
    "NGC4565": (12.6050, 25.9875, "Needle Galaxy", "Galaxy"),
    "NGC4631": (12.7033, 32.5414, "Whale Galaxy", "Galaxy"),
    "NGC4656": (12.7275, 32.1692, "Hockey Stick Galaxy", "Galaxy"),
    "NGC4725": (12.8442, 25.5006, "NGC 4725", "Galaxy"),
    "NGC5139": (13.4475, -47.4797, "Omega Centauri", "Globular Cluster"),
    "NGC5907": (15.2642, 56.3283, "Splinter Galaxy", "Galaxy"),
    "NGC6210": (16.7475, 23.7997, "Turtle Nebula", "Planetary Nebula"),
    "NGC6302": (17.2317, -37.1042, "Bug Nebula", "Planetary Nebula"),
    "NGC6334": (17.3417, -35.7833, "Cat's Paw Nebula", "Emission Nebula"),
    "NGC6543": (17.9767, 66.6328, "Cat's Eye Nebula", "Planetary Nebula"),
    "NGC6726": (19.0183, -36.9000, "NGC 6726", "Reflection Nebula"),
    "NGC6826": (19.7475, 50.5256, "Blinking Nebula", "Planetary Nebula"),
    "NGC6888": (20.2017, 38.3567, "Crescent Nebula", "Emission Nebula"),
    "NGC6960": (20.7617, 30.7100, "Western Veil Nebula", "Supernova Remnant"),
    "NGC6992": (20.9400, 31.7167, "Eastern Veil Nebula", "Supernova Remnant"),
    "NGC6995": (20.9567, 31.0333, "Veil Nebula (central)", "Supernova Remnant"),
    "NGC7000": (20.9750, 44.5333, "North America Nebula", "Emission Nebula"),
    "NGC7023": (21.0267, 68.1700, "Iris Nebula", "Reflection Nebula"),
    "NGC7293": (22.4933, -20.8375, "Helix Nebula", "Planetary Nebula"),
    "NGC7331": (22.6175, 34.4158, "NGC 7331", "Galaxy"),
    "NGC7380": (22.7867, 58.1333, "Wizard Nebula", "Emission Nebula"),
    "NGC7635": (23.3450, 61.2033, "Bubble Nebula", "Emission Nebula"),
    "NGC7789": (23.9567, 56.7167, "Caroline's Rose", "Open Cluster"),
    "NGC7822": (0.0500, 67.1333, "NGC 7822", "Emission Nebula"),
    "NGC7009": (21.0700, -11.3633, "Saturn Nebula", "Planetary Nebula"),
    "NGC7662": (23.4308, 42.5461, "Blue Snowball Nebula", "Planetary Nebula"),
    "NGC246": (0.7858, -11.8775, "Skull Nebula", "Planetary Nebula"),
    "NGC925": (2.4558, 33.5789, "NGC 925", "Galaxy"),
    "NGC3115": (10.0867, -7.7186, "Spindle Galaxy", "Galaxy"),
    "NGC6946": (20.5817, 60.1539, "Fireworks Galaxy", "Galaxy"),
}

# ~20 popular IC objects suitable for Seestar S50
IC_CATALOG = {
    "IC59": (0.9833, 61.0667, "IC 59 (Gamma Cas Nebula)", "Reflection Nebula"),
    "IC63": (0.9917, 60.9000, "Ghost of Cassiopeia", "Reflection Nebula"),
    "IC342": (3.7817, 68.0964, "Hidden Galaxy", "Galaxy"),
    "IC405": (5.2700, 34.2667, "Flaming Star Nebula", "Emission Nebula"),
    "IC410": (5.4733, 33.4833, "Tadpole Nebula", "Emission Nebula"),
    "IC417": (5.4717, 34.4167, "Spider Nebula", "Emission Nebula"),
    "IC434": (5.6833, -2.4500, "Horsehead Nebula region", "Emission Nebula"),
    "IC443": (6.2867, 22.5700, "Jellyfish Nebula", "Supernova Remnant"),
    "IC1283": (18.2900, -19.8167, "IC 1283", "Emission Nebula"),
    "IC1318": (20.2350, 40.3500, "Sadr Region / Gamma Cygni", "Emission Nebula"),
    "IC1396": (21.6467, 57.5000, "Elephant Trunk Nebula", "Emission Nebula"),
    "IC1613": (1.0817, 2.1250, "IC 1613 (dwarf galaxy)", "Galaxy"),
    "IC1795": (2.4567, 62.0833, "Fishhead Nebula", "Emission Nebula"),
    "IC1805": (2.5350, 61.4667, "Heart Nebula", "Emission Nebula"),
    "IC1848": (2.8533, 60.4500, "Soul Nebula", "Emission Nebula"),
    "IC2118": (5.0833, -7.2333, "Witch Head Nebula", "Reflection Nebula"),
    "IC2177": (7.0667, -10.4167, "Seagull Nebula", "Emission Nebula"),
    "IC4604": (16.4250, -24.3833, "Rho Ophiuchi Cloud", "Reflection Nebula"),
    "IC4665": (17.7267, 5.7167, "IC 4665", "Open Cluster"),
    "IC5067": (20.8083, 44.3667, "Pelican Nebula", "Emission Nebula"),
    "IC5070": (20.8333, 44.3667, "Pelican Nebula (core)", "Emission Nebula"),
    "IC5146": (21.8900, 47.2667, "Cocoon Nebula", "Emission Nebula"),
}


def _normalize_ngc_id(name: str) -> Optional[str]:
    """Normalize various NGC ID formats to 'NGC####'."""
    name = name.strip().upper().replace(" ", "")
    match = re.match(r"^NGC(\d{1,5})$", name)
    if match:
        return f"NGC{int(match.group(1))}"
    return None


def _normalize_ic_id(name: str) -> Optional[str]:
    """Normalize various IC ID formats to 'IC####'."""
    name = name.strip().upper().replace(" ", "")
    match = re.match(r"^IC(\d{1,5})$", name)
    if match:
        return f"IC{int(match.group(1))}"
    return None


def _entry_to_dict(catalog_id: str, entry: tuple) -> dict:
    """Convert a catalog tuple to a dict."""
    ra_hours, dec_deg, common_name, obj_type = entry
    return {
        "id": catalog_id,
        "ra_hours": ra_hours,
        "dec_degrees": dec_deg,
        "common_name": common_name,
        "object_type": obj_type,
    }


def lookup_ngc(name: str) -> Optional[dict]:
    """Look up an NGC object by ID.

    Accepts formats: "NGC7000", "ngc7000", "NGC 7000", "ngc 7000".
    Returns dict with id, ra_hours, dec_degrees, common_name, object_type
    or None if not found.
    """
    nid = _normalize_ngc_id(name)
    if nid and nid in NGC_CATALOG:
        return _entry_to_dict(nid, NGC_CATALOG[nid])
    return None


def lookup_ic(name: str) -> Optional[dict]:
    """Look up an IC object by ID.

    Accepts formats: "IC434", "ic434", "IC 434", "ic 434".
    Returns dict with id, ra_hours, dec_degrees, common_name, object_type
    or None if not found.
    """
    iid = _normalize_ic_id(name)
    if iid and iid in IC_CATALOG:
        return _entry_to_dict(iid, IC_CATALOG[iid])
    return None


def search_extended_catalog(query: str) -> list[dict]:
    """Search both NGC and IC catalogs by name, common name, or object type.

    Case-insensitive substring match.
    E.g., "veil" finds Veil Nebula entries, "galaxy" finds all galaxies.
    """
    query_lower = query.strip().lower()
    results = []
    for nid, entry in NGC_CATALOG.items():
        ra_hours, dec_deg, common_name, obj_type = entry
        if (
            query_lower in nid.lower()
            or query_lower in common_name.lower()
            or query_lower in obj_type.lower()
        ):
            results.append(_entry_to_dict(nid, entry))
    for iid, entry in IC_CATALOG.items():
        ra_hours, dec_deg, common_name, obj_type = entry
        if (
            query_lower in iid.lower()
            or query_lower in common_name.lower()
            or query_lower in obj_type.lower()
        ):
            results.append(_entry_to_dict(iid, entry))
    return results


def get_all_ngc() -> list[dict]:
    """Return all NGC objects as a list of dicts."""
    return [_entry_to_dict(nid, entry) for nid, entry in NGC_CATALOG.items()]


def get_all_ic() -> list[dict]:
    """Return all IC objects as a list of dicts."""
    return [_entry_to_dict(iid, entry) for iid, entry in IC_CATALOG.items()]


def get_all_extended() -> list[dict]:
    """Return all NGC + IC objects as a list of dicts."""
    return get_all_ngc() + get_all_ic()


# Alias for compatibility
get_all_extended_objects = get_all_extended
