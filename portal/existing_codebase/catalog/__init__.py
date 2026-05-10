"""SeestarScope star catalogs."""

from .messier import (
    MESSIER_CATALOG,
    lookup_messier,
    search_catalog,
    get_all_objects,
    get_objects_by_type,
)
from .ngc_ic import (
    NGC_CATALOG,
    IC_CATALOG,
    lookup_ngc,
    lookup_ic,
    search_extended_catalog,
    get_all_ngc,
    get_all_ic,
    get_all_extended,
    get_all_extended_objects,
)

__all__ = [
    "MESSIER_CATALOG",
    "lookup_messier",
    "search_catalog",
    "get_all_objects",
    "get_objects_by_type",
    "NGC_CATALOG",
    "IC_CATALOG",
    "lookup_ngc",
    "lookup_ic",
    "search_extended_catalog",
    "get_all_ngc",
    "get_all_ic",
    "get_all_extended",
    "get_all_extended_objects",
]
