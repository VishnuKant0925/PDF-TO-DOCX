"""
layout_analyzer.py — Column Detection & Reading Order

Detects the 2-column dictionary layout and sorts text into correct
reading order (left column top-to-bottom, then right column top-to-bottom).
Also separates the page header from the body.

Algorithm:
    1. Separate header (top ~6% of page) from body
    2. Build X-axis projection histogram from bounding boxes
    3. Find the largest gap → column separator
    4. Split boxes into columns, sort each top-to-bottom
"""

import numpy as np
import cv2
import os
from PIL import Image


def analyze(
    ocr_results: list[dict],
    image_width: int,
    image_height: int,
    forced_columns: int | None = None,
) -> tuple[dict, list[dict]]:
    """
    Analyze page layout: detect header and columns.

    Args:
        ocr_results: List of OCR result dicts from ocr_engine.
        image_width: Width of the page image in pixels.
        image_height: Height of the page image in pixels.
        forced_columns: If set, force this many columns (1, 2, or 3).

    Returns:
        Tuple of (header_dict, columns_list)
        header_dict: {left_word, page_number, right_word}
        columns_list: [{blocks: [...]}, {blocks: [...]}]
    """
    if not ocr_results:
        return {"left_word": "", "page_number": "", "right_word": ""}, []

    # Step 1: Separate header from body
    header, body_blocks = detect_header(ocr_results, image_height)

    # Step 2: Detect columns
    columns = detect_columns(body_blocks, image_width, forced_columns)

    return header, columns


def detect_header(
    ocr_results: list[dict], page_height: int
) -> tuple[dict, list[dict]]:
    """
    Separate header elements from body text.

    The page header is identified by text blocks in the top ~6% of the page.
    Typically contains: left guide word, page number (center), right guide word.

    Args:
        ocr_results: All OCR result dicts.
        page_height: Page image height in pixels.

    Returns:
        Tuple of (header_dict, body_blocks)
    """
    header_threshold = page_height * 0.06  # Top 6% of page

    header_blocks = [r for r in ocr_results if r["center_y"] < header_threshold]
    body_blocks = [r for r in ocr_results if r["center_y"] >= header_threshold]

    # Sort header blocks left to right
    header_blocks.sort(key=lambda r: r["center_x"])

    header = {"left_word": "", "page_number": "", "right_word": ""}

    if len(header_blocks) >= 3:
        header["left_word"] = header_blocks[0]["text"]
        # Page number is typically the middle element
        header["page_number"] = header_blocks[len(header_blocks) // 2]["text"]
        header["right_word"] = header_blocks[-1]["text"]
    elif len(header_blocks) == 2:
        # Could be: (left_word, page_number) or (page_number, right_word)
        # Heuristic: if one is a number, it's the page number
        if header_blocks[0]["text"].strip().isdigit():
            header["page_number"] = header_blocks[0]["text"]
            header["right_word"] = header_blocks[1]["text"]
        elif header_blocks[1]["text"].strip().isdigit():
            header["left_word"] = header_blocks[0]["text"]
            header["page_number"] = header_blocks[1]["text"]
        else:
            header["left_word"] = header_blocks[0]["text"]
            header["right_word"] = header_blocks[1]["text"]
    elif len(header_blocks) == 1:
        text = header_blocks[0]["text"].strip()
        if text.isdigit():
            header["page_number"] = text
        else:
            header["left_word"] = text

    return header, body_blocks


def detect_columns(
    body_blocks: list[dict],
    image_width: int,
    forced_columns: int | None = None,
) -> list[dict]:
    """
    Detect column boundaries using X-axis projection histogram,
    with center-point clustering as a fallback.

    Args:
        body_blocks: OCR result dicts (body only, no header).
        image_width: Page image width in pixels.
        forced_columns: Force column count if auto-detection fails.

    Returns:
        List of column dicts, each with "blocks" key containing sorted OCR results.
    """
    if not body_blocks:
        return [{"blocks": []}]

    # Force single column mode
    if forced_columns == 1:
        return [{"blocks": sorted(body_blocks, key=lambda r: r["center_y"])}]

    # --- Method 1: Histogram gap detection ---
    separator_pos = _find_separator_histogram(body_blocks, image_width)

    # --- Method 2 (fallback): Center-point clustering ---
    if separator_pos is None:
        separator_pos = _find_separator_center_clustering(body_blocks, image_width)

    # --- Forced columns fallback ---
    if separator_pos is None:
        if forced_columns and forced_columns >= 2:
            separator_pos = image_width // 2
        else:
            return [
                {"blocks": sorted(body_blocks, key=lambda r: r["center_y"])}
            ]

    # Split blocks into left and right columns
    left_blocks = [b for b in body_blocks if b["center_x"] < separator_pos]
    right_blocks = [b for b in body_blocks if b["center_x"] >= separator_pos]

    # Sort each column top-to-bottom
    left_blocks.sort(key=lambda r: r["center_y"])
    right_blocks.sort(key=lambda r: r["center_y"])

    columns = []
    if left_blocks:
        columns.append({"blocks": left_blocks})
    if right_blocks:
        columns.append({"blocks": right_blocks})

    # If no columns were formed, return single column
    if not columns:
        return [{"blocks": sorted(body_blocks, key=lambda r: r["center_y"])}]

    return columns


def _find_separator_histogram(
    body_blocks: list[dict], image_width: int
) -> int | None:
    """Find column separator via X-axis projection histogram gap."""
    histogram = np.zeros(image_width, dtype=np.float64)
    for block in body_blocks:
        x_min = int(max(0, block["bbox_rect"][0]))
        x_max = int(min(image_width, block["bbox_rect"][2]))
        if x_min < x_max:
            histogram[x_min:x_max] += 1

    # Smooth the histogram to remove noise
    kernel_size = max(1, image_width // 50)  # ~2% of width
    kernel = np.ones(kernel_size) / kernel_size
    histogram_smooth = np.convolve(histogram, kernel, mode="same")

    # Search in the middle 60% of the page (20%-80% of width)
    search_start = int(image_width * 0.2)
    search_end = int(image_width * 0.8)

    if search_start >= search_end:
        return None

    search_region = histogram_smooth[search_start:search_end]
    separator_pos = search_start + int(np.argmin(search_region))

    # Verify it's actually a gap (density should be notably lower than peak)
    max_density = np.max(histogram_smooth)
    if max_density > 0 and histogram_smooth[separator_pos] > max_density * 0.3:
        return None  # No clear gap found

    return separator_pos


def _find_separator_center_clustering(
    body_blocks: list[dict], image_width: int
) -> int | None:
    """
    Find column separator by clustering block center-X positions.

    If most blocks have their centers in either the left or right half,
    with a clear gap near the center, this detects a 2-column layout
    even when bounding boxes span the separator.
    """
    centers_x = sorted([b["center_x"] for b in body_blocks])

    if len(centers_x) < 10:
        return None  # Too few blocks to determine layout

    mid = image_width / 2
    margin = image_width * 0.15  # ±15% around center

    left_count = sum(1 for x in centers_x if x < mid - margin)
    right_count = sum(1 for x in centers_x if x > mid + margin)
    center_count = sum(1 for x in centers_x if mid - margin <= x <= mid + margin)

    # If most blocks cluster in left/right halves (and few are in the center
    # gap zone), it's a 2-column layout
    total = len(centers_x)
    if (left_count + right_count) > total * 0.7 and left_count > 5 and right_count > 5:
        # Find the best split point: largest gap between consecutive centers
        # in the middle region
        mid_centers = [x for x in centers_x if image_width * 0.3 < x < image_width * 0.7]

        if mid_centers:
            # Find largest gap between consecutive center positions
            best_gap = 0
            best_pos = int(mid)
            all_sorted = sorted(centers_x)
            for i in range(len(all_sorted) - 1):
                gap = all_sorted[i + 1] - all_sorted[i]
                pos = (all_sorted[i] + all_sorted[i + 1]) / 2
                if (image_width * 0.3 < pos < image_width * 0.7) and gap > best_gap:
                    best_gap = gap
                    best_pos = int(pos)

            if best_gap > image_width * 0.02:  # Gap must be at least 2% of width
                return best_pos

        # Fallback: use page center
        return int(mid)

    return None


def save_column_visualization(
    original_image: np.ndarray,
    header_blocks: list[dict],
    columns: list[dict],
    separator_x: int | None,
    output_path: str,
):
    """
    Draw column separator and color-coded blocks on the image for debugging.

    Colors: Red = header, Blue = left column, Green = right column
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    vis_image = original_image.copy()
    if len(vis_image.shape) == 2:
        vis_image = cv2.cvtColor(vis_image, cv2.COLOR_GRAY2BGR)
    elif vis_image.shape[2] == 3:
        vis_image = cv2.cvtColor(vis_image, cv2.COLOR_RGB2BGR)

    colors = [
        (255, 0, 0),    # Blue (BGR) - left column
        (0, 255, 0),    # Green (BGR) - right column
        (0, 255, 255),  # Yellow (BGR) - third column
    ]

    # Draw column separator
    if separator_x is not None:
        h = vis_image.shape[0]
        cv2.line(vis_image, (separator_x, 0), (separator_x, h), (0, 0, 255), 3)

    # Draw column blocks
    for col_idx, column in enumerate(columns):
        color = colors[col_idx % len(colors)]
        for block in column["blocks"]:
            bbox = block["bbox"]
            pts = np.array(bbox, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(vis_image, [pts], True, color, 2)

    cv2.imwrite(output_path, vis_image)
