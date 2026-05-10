"""Image processing utilities for SeestarScope.

Handles conversion of ALPACA imagearray responses to PIL Images,
histogram stretching for faint deep-sky objects, and image saving.
"""

import numpy as np
from PIL import Image
from typing import Optional
from pathlib import Path
from datetime import datetime


def alpaca_imagearray_to_image(image_data: list, color: bool = True) -> Optional[Image.Image]:
    """Convert ALPACA imagearray response to PIL Image.

    ALPACA returns image as a nested list of integers.
    For color sensors (Type=2), the array may be 3D: [x][y][channel].
    For mono sensors, it's 2D: [x][y].
    The Seestar S50 has a color sensor (sensortype=2), 1080x1920.
    """
    if not image_data:
        return None
    arr = np.array(image_data, dtype=np.uint32)
    # Handle 2D mono
    if arr.ndim == 2:
        arr = ((arr - arr.min()) / max(arr.max() - arr.min(), 1) * 255).astype(np.uint8)
        return Image.fromarray(arr, mode="L")
    # Handle 3D color
    elif arr.ndim == 3:
        arr = ((arr - arr.min()) / max(arr.max() - arr.min(), 1) * 255).astype(np.uint8)
        if arr.shape[2] == 3:
            return Image.fromarray(arr, mode="RGB")
        elif arr.shape[0] == 3:
            arr = np.transpose(arr, (1, 2, 0))
            return Image.fromarray(arr, mode="RGB")
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


def apply_stretch(
    image: Image.Image, black_point: float = 0.1, white_point: float = 99.9
) -> Image.Image:
    """Apply histogram stretch for better visibility of faint objects."""
    arr = np.array(image, dtype=np.float32)
    low = np.percentile(arr, black_point)
    high = np.percentile(arr, white_point)
    stretched = np.clip((arr - low) / max(high - low, 1) * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(stretched, mode=image.mode)
