"""Enhanced image processing with FITS metadata preservation.

Extends the original image_processing.py with:
- FITS file saving with full astronomical metadata
- Dual-format saving (FITS for data, PNG for preview)
- Database integration for gallery indexing
"""

import numpy as np
from PIL import Image
from astropy.io import fits
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def alpaca_imagearray_to_image(image_data: list, color: bool = True) -> Optional[Image.Image]:
    """Convert ALPACA imagearray response to PIL Image."""
    if not image_data:
        return None
    arr = np.array(image_data, dtype=np.uint32)
    if arr.ndim == 2:
        arr = ((arr - arr.min()) / max(arr.max() - arr.min(), 1) * 255).astype(np.uint8)
        return Image.fromarray(arr, mode='L')
    elif arr.ndim == 3:
        arr = ((arr - arr.min()) / max(arr.max() - arr.min(), 1) * 255).astype(np.uint8)
        if arr.shape[2] == 3:
            return Image.fromarray(arr, mode='RGB')
        elif arr.shape[0] == 3:
            arr = np.transpose(arr, (1, 2, 0))
            return Image.fromarray(arr, mode='RGB')
    return None


def save_image(image: Image.Image, target_name: str, save_dir: str = "captures") -> str:
    """Save captured image with metadata filename. Returns filepath."""
    path = Path(save_dir)
    path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = target_name.replace(" ", "_").replace("/", "_")
    filename = f"{safe_name}_{timestamp}.png"
    filepath = path / filename
    image.save(str(filepath))
    return str(filepath)


def apply_stretch(image: Image.Image, black_point: float = 0.1, white_point: float = 99.9) -> Image.Image:
    """Apply histogram stretch for better visibility of faint objects."""
    arr = np.array(image, dtype=np.float32)
    low = np.percentile(arr, black_point)
    high = np.percentile(arr, white_point)
    stretched = np.clip((arr - low) / max(high - low, 1) * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(stretched, mode=image.mode)


# ============================================================================
# FITS Metadata Preservation
# ============================================================================

def create_fits_header(metadata: Dict[str, Any]) -> fits.Header:
    """Create FITS header from Seestar/ALPACA metadata."""
    header = fits.Header()

    header['SIMPLE'] = True
    header['BITPIX'] = 16
    header['NAXIS'] = 2

    header['TELESCOP'] = ('Seestar S50', 'Telescope model')
    header['INSTRUME'] = ('Sony IMX462', 'Detector name')
    header['OBSERVER'] = ('SeestarScope', 'Observer/Software')

    if 'target' in metadata:
        header['OBJECT'] = (metadata['target'], 'Target object name')

    if 'exposure' in metadata:
        header['EXPTIME'] = (float(metadata['exposure']), 'Exposure time (seconds)')
    if 'gain' in metadata:
        header['GAIN'] = (int(metadata['gain']), 'Sensor gain (0-400)')
    if 'filter' in metadata:
        header['FILTER'] = (str(metadata['filter']), 'Filter name')

    if 'ra' in metadata and metadata['ra'] is not None:
        header['RA'] = (float(metadata['ra']), 'Right ascension (hours, J2000)')
        header['OBJCTRA'] = (format_ra_hms(metadata['ra']), 'RA in HH:MM:SS.S')
    if 'dec' in metadata and metadata['dec'] is not None:
        header['DEC'] = (float(metadata['dec']), 'Declination (degrees, J2000)')
        header['OBJCTDEC'] = (format_dec_dms(metadata['dec']), 'Dec in +DD:MM:SS')

    if 'temperature' in metadata and metadata['temperature'] is not None:
        header['CCD-TEMP'] = (float(metadata['temperature']), 'CCD temperature (Celsius)')

    if 'timestamp' in metadata:
        header['DATE-OBS'] = (metadata['timestamp'], 'Observation start time (UTC)')
    else:
        header['DATE-OBS'] = (datetime.utcnow().isoformat(), 'Observation start time (UTC)')

    header['XPIXSZ'] = (2.9, 'Pixel width (microns)')
    header['YPIXSZ'] = (2.9, 'Pixel height (microns)')
    header['XBINNING'] = (1, 'Horizontal binning factor')
    header['YBINNING'] = (1, 'Vertical binning factor')
    header['BAYERPAT'] = ('RGGB', 'Bayer pattern')
    header['COLORTYP'] = ('RGGB', 'Color type')

    if 'telescope_status' in metadata:
        ts = metadata['telescope_status']
        if 'tracking' in ts:
            header['TRACKING'] = (bool(ts['tracking']), 'Sidereal tracking enabled')
        if 'at_park' in ts:
            header['ATPARK'] = (bool(ts['at_park']), 'Telescope parked')

    if 'camera_status' in metadata:
        cs = metadata['camera_status']
        if 'state' in cs:
            header['CAMSTATE'] = (str(cs['state']), 'Camera state at capture')

    header['SWCREATE'] = ('SeestarScope', 'Software creator')
    header['SWVER'] = ('1.0.0', 'Software version')

    header['COMMENT'] = 'Raw frame from Seestar S50 via ASCOM ALPACA'
    header['COMMENT'] = 'Saved by SeestarScope with full metadata preservation'

    return header


def format_ra_hms(ra_hours: float) -> str:
    """Format RA in hours to HH:MM:SS.S string."""
    hours = int(ra_hours)
    minutes = int((ra_hours - hours) * 60)
    seconds = ((ra_hours - hours) * 60 - minutes) * 60
    return f"{hours:02d}:{minutes:02d}:{seconds:04.1f}"


def format_dec_dms(dec_degrees: float) -> str:
    """Format Dec in degrees to +/-DD:MM:SS string."""
    sign = '+' if dec_degrees >= 0 else '-'
    dec_abs = abs(dec_degrees)
    degrees = int(dec_abs)
    minutes = int((dec_abs - degrees) * 60)
    seconds = ((dec_abs - degrees) * 60 - minutes) * 60
    return f"{sign}{degrees:02d}:{minutes:02d}:{seconds:04.1f}"


def save_fits(
    image_data: np.ndarray,
    metadata: Dict[str, Any],
    target_name: str,
    save_dir: str = "captures/fits"
) -> str:
    """Save image as FITS file with full astronomical metadata."""
    path = Path(save_dir)
    path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = target_name.replace(" ", "_").replace("/", "_")
    filename = f"{safe_name}_{timestamp}.fits"
    filepath = path / filename

    header = create_fits_header(metadata)

    if image_data.dtype == np.uint32:
        image_data = (image_data / (2**16)).astype(np.uint16)
    elif image_data.dtype == np.uint8:
        logger.warning("Image data is uint8 (normalized). Original bit depth lost.")

    hdu = fits.PrimaryHDU(data=image_data, header=header)

    try:
        hdu.writeto(str(filepath), overwrite=True)
        logger.info(f"FITS saved: {filepath}")
        return str(filepath)
    except Exception as e:
        logger.error(f"Failed to save FITS: {e}")
        raise


def save_dual_format(
    image_data_raw: np.ndarray,
    image_pil: Image.Image,
    metadata: Dict[str, Any],
    target_name: str,
    save_dir: str = "captures"
) -> Dict[str, str]:
    """Save image in both FITS (with metadata) and PNG (for preview)."""
    fits_path = save_fits(
        image_data_raw,
        metadata,
        target_name,
        save_dir=str(Path(save_dir) / "fits")
    )
    png_path = save_image(
        image_pil,
        target_name,
        save_dir=str(Path(save_dir) / "png")
    )
    return {
        'fits': fits_path,
        'png': png_path,
        'target': target_name,
        'timestamp': datetime.utcnow().isoformat()
    }


def prepare_metadata_from_alpaca(
    alpaca_client,
    target_name: str,
    exposure: float,
    gain: int
) -> Dict[str, Any]:
    """Extract metadata from AlpacaClient for FITS header."""
    metadata = {
        'target': target_name,
        'exposure': exposure,
        'gain': gain,
        'timestamp': datetime.utcnow().isoformat()
    }

    try:
        tel_status = alpaca_client.get_telescope_status()
        metadata['ra'] = tel_status.get('ra')
        metadata['dec'] = tel_status.get('dec')
        metadata['telescope_status'] = tel_status
    except Exception as e:
        logger.warning(f"Could not get telescope status: {e}")

    try:
        cam_status = alpaca_client.get_camera_status()
        metadata['camera_status'] = cam_status
    except Exception as e:
        logger.warning(f"Could not get camera status: {e}")

    try:
        filter_names = alpaca_client.get_filter_names()
        filter_pos = alpaca_client.get_filter_position()
        if filter_names and filter_pos is not None and filter_pos < len(filter_names):
            metadata['filter'] = filter_names[filter_pos]
    except Exception as e:
        logger.warning(f"Could not get filter: {e}")

    try:
        focuser_status = alpaca_client.get_focuser_status()
        metadata['temperature'] = focuser_status.get('temperature')
    except Exception as e:
        logger.warning(f"Could not get focuser temperature: {e}")

    return metadata
