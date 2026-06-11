"""
renderer.py — PDF page → high-res image

Renders each PDF page as a high-resolution PNG image for OCR processing.
Uses PyMuPDF (pymupdf) for fast, accurate rendering.

Default DPI is 400 (higher than standard 300) to capture thin strokes
in Devanagari conjuncts (e.g., क्ष, त्र).
"""

import os
import numpy as np
from PIL import Image

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf


def get_page_count(pdf_path: str) -> int:
    """Get total number of pages in the PDF."""
    doc = pymupdf.open(pdf_path)
    count = len(doc)
    doc.close()
    return count


def render_page(pdf_path: str, page_num: int, dpi: int = 400) -> dict:
    """
    Render a single PDF page as a high-res image.

    Args:
        pdf_path: Path to the PDF file.
        page_num: 0-indexed page number.
        dpi: Resolution for rendering (default 400).

    Returns:
        dict with keys:
            image_np   - numpy.ndarray (H x W x 3, uint8, RGB)
            image_pil  - PIL.Image (RGB)
            page_number - int (0-indexed)
            width_px   - int (rendered image width in pixels)
            height_px  - int (rendered image height in pixels)
            width_pt   - float (original PDF page width in points)
            height_pt  - float (original PDF page height in points)
    """
    doc = pymupdf.open(pdf_path)

    if page_num < 0 or page_num >= len(doc):
        doc.close()
        raise ValueError(
            f"Page {page_num} out of range (PDF has {len(doc)} pages, 0-indexed)"
        )

    page = doc[page_num]

    # Calculate zoom factor: PDF default is 72 DPI
    zoom = dpi / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)

    # Render to pixmap (RGB, no alpha)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)

    # Convert to numpy array (H x W x 3)
    image_np = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.width, 3
    ).copy()  # .copy() to own the memory after doc.close()

    # Convert to PIL Image
    image_pil = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

    result = {
        "image_np": image_np,
        "image_pil": image_pil,
        "page_number": page_num,
        "width_px": pixmap.width,
        "height_px": pixmap.height,
        "width_pt": page.rect.width,
        "height_pt": page.rect.height,
    }

    doc.close()
    return result


def save_debug_image(image_np: np.ndarray, path: str):
    """Save a numpy image array to disk for debugging."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = Image.fromarray(image_np)
    img.save(path)
