"""Gallery View - Browse captured images with filtering

Displays image gallery from FastAPI backend (seestar-portal-backend:8503).
Shows thumbnails, metadata, filtering controls, and processing status.
"""

import os
import urllib.parse
import streamlit as st
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Backend API base URL
BACKEND_URL = os.environ.get("BACKEND_URL", "http://seestar-portal-backend:8503")


def render_gallery():
    """Main gallery view rendering function."""
    st.title("📸 Image Gallery")
    st.markdown("Browse captured images with metadata, filters, and processing status")

    # Check backend connectivity
    if not check_backend_health():
        st.error(
            f"⚠️ Backend API is not reachable at {BACKEND_URL}. Start the FastAPI backend first."
        )
        st.code("cd backend && uvicorn main:app --host 0.0.0.0 --port 8503", language="bash")
        return

    pp_healthy = check_postprocessing_health()
    if not pp_healthy:
        st.warning("⚠️ Post-processing service is unreachable — Process buttons disabled.")

    st.divider()

    # Filter controls
    with st.expander("🔍 Filter Options", expanded=False):
        filters = render_filter_controls()

    source = st.selectbox(
        "Source",
        ["All", "Local captures", "Scope onboard"],
        key="gallery_source",
        help="Local captures live in the portal's SQLite DB; Scope onboard reads "
        "the Seestar's built-in archive over :4701.",
    )

    # Fetch items once; pass count into stats to avoid a second :4701 round-trip.
    local_images = fetch_images(filters) if source in ("All", "Local captures") else []
    onboard_items = fetch_onboard_items() if source in ("All", "Scope onboard") else []

    # Display gallery stats
    render_gallery_stats(onboard_count=len(onboard_items))

    if not local_images and not onboard_items:
        st.info("No images found. Capture some images first, or check the scope connection.")
        return

    render_image_grid(local_images, onboard_items=onboard_items, pp_healthy=pp_healthy)


def check_backend_health() -> bool:
    """Check if FastAPI backend is reachable."""
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def check_postprocessing_health() -> bool:
    """Check if the postprocessing endpoint is reachable and healthy."""
    try:
        return requests.get(f"{BACKEND_URL}/api/postprocessing/health", timeout=2).ok
    except requests.exceptions.ConnectionError as exc:
        logger.debug("Postprocessing health check: connection refused: %s", exc)
        return False
    except requests.exceptions.Timeout:
        logger.debug("Postprocessing health check: timed out after 2s")
        return False
    except Exception as exc:
        logger.debug("Postprocessing health check failed: %s", exc)
        return False


def render_gallery_stats(onboard_count: int = 0):
    """Display gallery statistics summary."""
    try:
        response = requests.get(f"{BACKEND_URL}/api/gallery/stats", timeout=5)
        if response.status_code == 200:
            stats = response.json()

            col1, col2, col3, col4, col5 = st.columns(5)

            with col1:
                st.metric("Total Images", stats["total_images"])

            with col2:
                st.metric("Sessions", stats["total_sessions"])

            with col3:
                st.metric("Processed", stats["processed_count"])

            with col4:
                hours = stats["total_exposure_hours"]
                st.metric("Total Exposure", f"{hours:.1f}h")

            with col5:
                st.metric("Scope Onboard", onboard_count)

            # Target breakdown
            if stats.get("targets"):
                st.markdown("**Targets:**")
                target_cols = st.columns(min(len(stats["targets"]), 5))
                for idx, (target, count) in enumerate(list(stats["targets"].items())[:5]):
                    with target_cols[idx]:
                        st.caption(f"{target}: {count}")

    except Exception as e:
        logger.error("Failed to fetch gallery stats: %s", e, exc_info=True)
        st.warning("Could not load gallery statistics")


def render_filter_controls() -> Dict[str, Any]:
    """Render filter controls and return filter parameters."""
    filters = {}

    col1, col2 = st.columns(2)

    with col1:
        target = st.text_input("Target Name", placeholder="M31, NGC7000, etc.")
        if target:
            filters["target"] = target

        date_range = st.date_input("Date Range", value=[], help="Select start and/or end date")
        if len(date_range) == 2:
            filters["start_date"] = datetime.combine(date_range[0], datetime.min.time()).isoformat()
            filters["end_date"] = datetime.combine(date_range[1], datetime.max.time()).isoformat()
        elif len(date_range) == 1:
            filters["start_date"] = datetime.combine(date_range[0], datetime.min.time()).isoformat()

    with col2:
        filter_type = st.selectbox("Filter", ["All", "L", "R", "G", "B", "Ha", "OIII", "SII"])
        if filter_type != "All":
            filters["filter"] = filter_type

        status_cols = st.columns(2)
        with status_cols[0]:
            processed_only = st.checkbox("Processed only")
            if processed_only:
                filters["processed_only"] = True

        with status_cols[1]:
            stacked_only = st.checkbox("Stacked only")
            if stacked_only:
                filters["stacked_only"] = True

    # Exposure range
    exp_col1, exp_col2 = st.columns(2)
    with exp_col1:
        min_exp = st.number_input("Min Exposure (s)", min_value=0.0, value=0.0, step=1.0)
        if min_exp > 0:
            filters["min_exposure"] = min_exp

    with exp_col2:
        max_exp = st.number_input("Max Exposure (s)", min_value=0.0, value=0.0, step=1.0)
        if max_exp > 0:
            filters["max_exposure"] = max_exp

    # Results limit
    limit = st.slider("Results per page", min_value=10, max_value=100, value=50, step=10)
    filters["limit"] = limit

    return filters


def fetch_images(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fetch images from backend with filters."""
    try:
        response = requests.get(f"{BACKEND_URL}/api/gallery/", params=filters, timeout=10)

        if response.status_code == 200:
            images = response.json()
            logger.info("Fetched %d images from gallery", len(images))
            return images
        else:
            st.error(f"Failed to fetch images: {response.status_code}")
            return []

    except Exception as e:
        logger.error("Error fetching images: %s", e, exc_info=True)
        st.error(f"Error fetching images: {e}")
        return []


def fetch_onboard_items() -> List[Dict[str, Any]]:
    """Fetch the scope's onboard archive listing from the backend."""
    try:
        response = requests.get(f"{BACKEND_URL}/api/gallery/onboard/", timeout=10)
        if response.status_code == 200:
            return response.json()
        logger.warning("Onboard fetch HTTP %s: %s", response.status_code, response.text[:200])
        return []
    except Exception as exc:
        logger.error("Error fetching onboard items: %s", exc, exc_info=True)
        return []


def render_image_grid(
    images: List[Dict[str, Any]],
    onboard_items: Optional[List[Dict[str, Any]]] = None,
    pp_healthy: bool = False,
):
    """Render local + onboard items in a responsive grid."""
    onboard_items = onboard_items or []
    all_items = [("local", img) for img in images] + [("onboard", item) for item in onboard_items]
    st.markdown(
        f"### Showing {len(all_items)} items ({len(images)} local, {len(onboard_items)} onboard)"
    )

    for idx in range(0, len(all_items), 3):
        cols = st.columns(3)
        for col, (kind, item) in zip(cols, all_items[idx : idx + 3]):
            with col:
                if kind == "local":
                    render_image_card(item, pp_healthy=pp_healthy)
                else:
                    render_onboard_card(item)


def render_onboard_card(item: Dict[str, Any]):
    """Render a single onboard (scope-resident) item card."""
    with st.container():
        is_video = item.get("is_video", False)
        if is_video:
            st.caption("🎬 Video (requires direct LAN access to scope)")
            st.video(item["full_url"])  # browser fetches directly from scope :80
        else:
            path_part = urllib.parse.urlparse(item["thumb_url"]).path.lstrip("/")
            encoded = urllib.parse.quote(path_part, safe="/")
            thumb_proxy = f"{BACKEND_URL}/api/gallery/onboard/thumbnail?path={encoded}"
            try:
                resp = requests.get(thumb_proxy, timeout=10)
                resp.raise_for_status()
                st.image(resp.content, use_container_width=True)
            except Exception as exc:
                logger.warning("render_onboard_card: thumbnail load failed: %s", exc, exc_info=True)
                st.error("Failed to load thumbnail")
        st.markdown(f"**{item.get('name', '(unnamed)')}**")
        st.caption("📷 Scope onboard")


def render_image_card(image: Dict[str, Any], pp_healthy: bool = False):
    """Render a single image card with thumbnail and metadata."""
    with st.container():
        # Image thumbnail (or processed preview when toggled on)
        if image.get("processed") and image.get("processed_path"):
            show_processed = st.checkbox(
                "Show Processed",
                value=True,
                key=f"show_proc_{image['id']}",
            )
            if show_processed:
                thumbnail_url = (
                    f"{BACKEND_URL}/api/gallery/{image['id']}/thumbnail?size=256&processed=true"
                )
            else:
                thumbnail_url = f"{BACKEND_URL}/api/gallery/{image['id']}/thumbnail?size=256"
        else:
            thumbnail_url = f"{BACKEND_URL}/api/gallery/{image['id']}/thumbnail?size=256"

        try:
            st.image(thumbnail_url, use_container_width=True)
        except Exception:
            st.error("Failed to load thumbnail")

        # Metadata
        metadata = image["metadata"]

        st.markdown(f"**{metadata['target']}**")
        st.caption(f"🕐 {format_timestamp(image['captured_at'])}")

        # Technical details in compact format
        st.caption(f"⏱️ {metadata['exposure']}s @ Gain {metadata['gain']}")

        # Processing status badges
        badge_cols = st.columns(2)
        with badge_cols[0]:
            if image.get("processed"):
                st.success("✓ Processed", help="Image has been processed")

        with badge_cols[1]:
            if image.get("stacked"):
                st.info("📚 Stacked", help="Part of stacked sequence")

        # Process button (kicks off backend pipeline)
        if pp_healthy:
            if st.button("Process", key=f"process_{image['id']}"):
                try:
                    resp = requests.post(
                        f"{BACKEND_URL}/api/postprocessing/apply",
                        json={
                            "image_path": image.get("png_path") or image.get("fits_path"),
                            "stretch": "stf",
                            "color_balance": True,
                        },
                        timeout=5,
                    )
                    if resp.ok:
                        st.success(f"Processing started: job {resp.json().get('job_id')}")
                    else:
                        try:
                            detail = resp.json().get("detail", resp.text)
                        except Exception:
                            detail = f"HTTP {resp.status_code}"
                        logger.error(
                            "Processing request failed (HTTP %s): %s", resp.status_code, resp.text
                        )
                        st.error(f"Processing failed: {detail}")
                except Exception as exc:
                    st.error(f"Processing request failed: {exc}")
        else:
            st.caption("(post-processing offline)")

        # Session ID
        st.caption(f"Session: `{image['session_id']}`")

        # Expander for full details
        with st.expander("Details"):
            render_image_details(image)


def render_image_details(image: Dict[str, Any]):
    """Render full image details in expander."""
    metadata = image["metadata"]

    st.json(
        {
            "ID": image["id"],
            "Target": metadata["target"],
            "Exposure": f"{metadata['exposure']}s",
            "Gain": metadata["gain"],
            "Filter": metadata["filter"],
            "RA": metadata.get("ra"),
            "Dec": metadata.get("dec"),
            "Temperature": f"{metadata.get('temperature')}°C"
            if metadata.get("temperature")
            else None,
            "Telescope": metadata.get("telescope", "Seestar S50"),
            "Session": image["session_id"],
            "Captured": image["captured_at"],
            "Processed": image.get("processed"),
            "Stacked": image.get("stacked"),
        }
    )

    # File paths
    st.markdown("**Files:**")
    st.code(image["fits_path"], language="text")
    st.code(image["png_path"], language="text")

    # Tags if present
    if image.get("tags"):
        st.markdown("**Tags:**")
        st.write(", ".join(image["tags"]))

    # Notes if present
    if image.get("notes"):
        st.markdown("**Notes:**")
        st.write(image["notes"])


def format_timestamp(timestamp_str: str) -> str:
    """Format ISO timestamp to readable string."""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return timestamp_str
