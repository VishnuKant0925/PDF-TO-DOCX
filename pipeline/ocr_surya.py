"""
ocr_surya.py — Surya OCR Wrapper for Hindi + English

Provides the same interface as ocr_engine.py but uses Surya OCR (v0.6.x)
with PyTorch + CUDA instead of PaddleOCR.

Uses a GPU-aware approach with small recognition batch sizes to fit
within 6GB VRAM on RTX 3050 GPUs.

Usage:
    models = load_models()
    results = run_ocr(image_pil, models, languages=["en", "hi"])
"""

import os
import gc
import numpy as np
from PIL import Image, ImageDraw
import torch

# Configure Surya batch sizes BEFORE importing surya modules.
# Default CUDA batch size is 512 — way too high for 6GB VRAM.
os.environ["RECOGNITION_BATCH_SIZE"] = "32"
os.environ["RECOGNITION_ENCODER_BATCH_DIVISOR"] = "4"

# Surya v0.6.x imports
from surya.ocr import run_ocr as surya_run_ocr
from surya.model.detection.model import load_model as load_det_model, load_processor as load_det_processor
from surya.model.recognition.model import load_model as load_rec_model
from surya.model.recognition.processor import load_processor as load_rec_processor


def load_models() -> dict:
    """
    Load Surya detection and recognition models.

    Returns a dict with all four model components.
    First call downloads weights from HuggingFace (~1.5GB total).
    Subsequent calls load from cache.
    """
    det_model = load_det_model()
    det_processor = load_det_processor()
    rec_model = load_rec_model()
    rec_processor = load_rec_processor()

    return {
        "det_model": det_model,
        "det_processor": det_processor,
        "rec_model": rec_model,
        "rec_processor": rec_processor,
    }


def _free_gpu_memory():
    """Force free GPU memory — critical between pages on 6GB GPUs."""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()


def run_ocr(
    image_pil: Image.Image,
    models: dict,
    languages: list[str] | None = None,
) -> list[dict]:
    """
    Run Surya OCR on a single page image.

    Uses surya.ocr.run_ocr internally with controlled batch sizes
    to prevent CUDA OOM on 6GB VRAM GPUs.

    Args:
        image_pil: PIL Image (RGB) of the page.
        models: Dict from load_models().
        languages: List of language codes (default: ["en", "hi"]).

    Returns:
        List of dicts, each with:
            text, confidence, bbox, bbox_rect, center_x, center_y
    """
    if languages is None:
        languages = ["en", "hi"]

    # Use surya's high-level run_ocr (handles detection + slicing + recognition)
    predictions = surya_run_ocr(
        [image_pil],
        [languages],
        models["det_model"],
        models["det_processor"],
        models["rec_model"],
        models["rec_processor"],
    )

    result = predictions[0]
    ocr_results = []

    for text_line in result.text_lines:
        text = text_line.text
        confidence = text_line.confidence
        bbox = text_line.bbox  # [x1, y1, x2, y2] in Surya v0.6

        x_min, y_min, x_max, y_max = bbox

        # Convert to 4-corner format for compatibility with existing layout_analyzer
        bbox_corners = [
            [x_min, y_min],  # top-left
            [x_max, y_min],  # top-right
            [x_max, y_max],  # bottom-right
            [x_min, y_max],  # bottom-left
        ]

        ocr_results.append({
            "text": text,
            "confidence": confidence,
            "bbox": bbox_corners,
            "bbox_rect": [x_min, y_min, x_max, y_max],
            "center_x": (x_min + x_max) / 2,
            "center_y": (y_min + y_max) / 2,
            "width": x_max - x_min,
            "height": y_max - y_min,
        })

    # Free GPU memory between pages (critical for 6GB VRAM GPUs)
    del predictions, result
    _free_gpu_memory()

    return ocr_results


def get_confidence_stats(ocr_results: list[dict]) -> dict:
    """Compute confidence statistics for OCR results."""
    if not ocr_results:
        return {
            "total_count": 0,
            "avg_confidence": 0.0,
            "min_confidence": 0.0,
            "max_confidence": 0.0,
            "low_count": 0,
        }

    confidences = [r["confidence"] for r in ocr_results]
    return {
        "total_count": len(confidences),
        "avg_confidence": sum(confidences) / len(confidences),
        "min_confidence": min(confidences),
        "max_confidence": max(confidences),
        "low_count": sum(1 for c in confidences if c < 0.7),
    }


def save_ocr_visualization(
    image_np: np.ndarray,
    ocr_results: list[dict],
    output_path: str,
):
    """
    Draw OCR bounding boxes on the image and save for debugging.

    Green = high confidence (>=0.7), Red = low confidence (<0.7).
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    image_pil = Image.fromarray(image_np)
    draw = ImageDraw.Draw(image_pil)

    for result in ocr_results:
        x1, y1, x2, y2 = result["bbox_rect"]
        color = "green" if result["confidence"] >= 0.7 else "red"
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
        draw.text((x1, max(y1 - 12, 0)), f"{result['confidence']:.2f}", fill=color)

    image_pil.save(output_path)
