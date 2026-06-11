"""
preprocessor.py — Image cleanup for OCR

Cleans up rendered PDF page images to maximize OCR accuracy
on small, dense dictionary text.

Pipeline:
    Raw Image → Grayscale → CLAHE → Adaptive Threshold
              → Denoise → Deskew → Border Crop → Output

Each step is independently toggleable. In debug mode, saves
the image after each step for visual inspection.
"""

import os
import numpy as np
import cv2
from PIL import Image


# Default preprocessing configuration
DEFAULT_CONFIG = {
    "enable_grayscale": True,
    "enable_clahe": True,
    "enable_threshold": True,
    "enable_denoise": True,
    "enable_deskew": True,
    "enable_crop": True,
    # Parameters
    "clahe_clip_limit": 2.0,
    "clahe_grid_size": (8, 8),
    "threshold_block_size": 15,
    "threshold_c": 8,
    "denoise_kernel_size": 2,
    "deskew_min_line_length": 100,
    "crop_padding": 20,
}


def preprocess(
    image_np: np.ndarray,
    config: dict | None = None,
    debug_path: str | None = None,
) -> np.ndarray:
    """
    Run the full preprocessing pipeline on a page image.

    Args:
        image_np: Input image as numpy array (H x W x 3, RGB).
        config: Override default preprocessing parameters.
        debug_path: If provided, save intermediate images to this directory.

    Returns:
        Processed image as numpy array (grayscale or binary).
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    img = image_np.copy()

    if debug_path:
        os.makedirs(debug_path, exist_ok=True)

    # Step 1: Grayscale conversion
    if cfg["enable_grayscale"] and len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        if debug_path:
            _save_debug(img, os.path.join(debug_path, "01_gray.png"))

    # Step 2: CLAHE (Contrast Limited Adaptive Histogram Equalization)
    if cfg["enable_clahe"]:
        img = _apply_clahe(img, cfg["clahe_clip_limit"], cfg["clahe_grid_size"])
        if debug_path:
            _save_debug(img, os.path.join(debug_path, "02_clahe.png"))

    # Step 3: Adaptive thresholding (binarization)
    if cfg["enable_threshold"]:
        img = _apply_threshold(
            img, cfg["threshold_block_size"], cfg["threshold_c"]
        )
        if debug_path:
            _save_debug(img, os.path.join(debug_path, "03_threshold.png"))

    # Step 4: Denoising (morphological opening)
    if cfg["enable_denoise"]:
        img = _apply_denoise(img, cfg["denoise_kernel_size"])
        if debug_path:
            _save_debug(img, os.path.join(debug_path, "04_denoise.png"))

    # Step 5: Deskewing
    if cfg["enable_deskew"]:
        img = _apply_deskew(img, cfg["deskew_min_line_length"])
        if debug_path:
            _save_debug(img, os.path.join(debug_path, "05_deskew.png"))

    # Step 6: Border cropping
    if cfg["enable_crop"]:
        img = _apply_crop(img, cfg["crop_padding"])
        if debug_path:
            _save_debug(img, os.path.join(debug_path, "06_cropped.png"))

    # Save final preprocessed result
    if debug_path:
        _save_debug(img, os.path.join(debug_path, "preprocessed.png"))

    return img


def _apply_clahe(
    image_gray: np.ndarray, clip_limit: float, grid_size: tuple
) -> np.ndarray:
    """Enhance contrast using CLAHE — improves faint text visibility."""
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=grid_size)
    return clahe.apply(image_gray)


def _apply_threshold(
    image_gray: np.ndarray, block_size: int, c: int
) -> np.ndarray:
    """Binarize with local adaptive thresholds — handles uneven paper color."""
    # Ensure block_size is odd and >= 3
    if block_size % 2 == 0:
        block_size += 1
    if block_size < 3:
        block_size = 3
    return cv2.adaptiveThreshold(
        image_gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size,
        c,
    )


def _apply_denoise(image: np.ndarray, kernel_size: int) -> np.ndarray:
    """Remove tiny speckles that confuse OCR using morphological opening."""
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    return cv2.morphologyEx(image, cv2.MORPH_OPEN, kernel)


def _apply_deskew(image: np.ndarray, min_line_length: int) -> np.ndarray:
    """
    Detect page rotation and correct it.

    Uses Hough line detection to find the dominant angle of
    near-horizontal lines, then rotates to correct skew.
    Even 0.5° rotation significantly hurts small-text OCR.
    """
    # Edge detection
    edges = cv2.Canny(image, 50, 150, apertureSize=3)

    # Detect lines using Probabilistic Hough Transform
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=200,
        minLineLength=min_line_length,
        maxLineGap=10,
    )

    if lines is None:
        return image  # No lines detected, skip

    # Calculate angles of all detected lines
    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        # Only consider near-horizontal lines (±10°)
        if abs(angle) < 10:
            angles.append(angle)

    if not angles:
        return image

    # Median angle is more robust than mean against outliers
    median_angle = np.median(angles)

    # Skip if rotation is negligibly small
    if abs(median_angle) < 0.1:
        return image

    # Rotate image to correct skew
    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    rotation_matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    corrected = cv2.warpAffine(
        image,
        rotation_matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return corrected


def _apply_crop(image: np.ndarray, padding: int) -> np.ndarray:
    """
    Crop black/white borders to content area.

    Detects large white margins around the content and crops them,
    keeping a small padding for OCR context.
    """
    # If binary image, invert to find content (black text on white = content is black)
    if len(image.shape) == 2:
        # Invert: white background (255) → 0, black text → 255
        inverted = cv2.bitwise_not(image)
    else:
        inverted = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        inverted = cv2.bitwise_not(inverted)

    # Find bounding rect of all non-zero (content) pixels
    coords = cv2.findNonZero(inverted)
    if coords is None:
        return image  # No content found

    x, y, w, h = cv2.boundingRect(coords)

    # Add padding
    img_h, img_w = image.shape[:2]
    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(img_w, x + w + padding)
    y2 = min(img_h, y + h + padding)

    return image[y1:y2, x1:x2]


def _save_debug(image: np.ndarray, path: str):
    """Save image to disk for debugging."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if len(image.shape) == 2:
        # Grayscale
        Image.fromarray(image, mode="L").save(path)
    else:
        Image.fromarray(image).save(path)
