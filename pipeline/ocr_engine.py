"""
ocr_engine.py — PaddleOCR wrapper for Hindi + English

Runs OCR on preprocessed page images using PaddleOCR's Hindi model,
which handles both Devanagari and Latin scripts in a single pass.

GPU acceleration is used when available (NVIDIA CUDA).
"""

import os
import sys
import types
import numpy as np
import cv2
from PIL import Image


# ---------------------------------------------------------------------------
# Workaround: Mock PyTorch to bypass broken shm.dll on this Windows system.
#
# PaddleOCR does NOT use PyTorch — it uses PaddlePaddle. However, its
# transitive dependencies (albumentations, modelscope) do `import torch`
# at module level, which crashes if torch's native DLLs are broken.
#
# This mock provides just enough structure for those imports to succeed.
# ---------------------------------------------------------------------------
def _ensure_torch_mock():
    """Install a lightweight torch mock if real torch can't load."""
    if "torch" in sys.modules:
        return  # Already loaded (real or mock)

    try:
        import torch  # noqa: F401 — test if real torch loads
    except (OSError, ImportError):
        # Real torch is broken — install mock
        _mock = types.ModuleType("torch")
        _mock.__version__ = "0.0.0+mock"
        _mock.__file__ = "mock"
        _mock.__path__ = []

        # Minimal class stubs that albumentations.pytorch expects
        _mock.Tensor = type("Tensor", (), {"__module__": "torch"})
        _mock.device = type("device", (), {"__module__": "torch", "__init__": lambda self, *a, **kw: None})
        _mock.float32 = "float32"
        _mock.no_grad = lambda: type("ctx", (), {"__enter__": lambda s: None, "__exit__": lambda s, *a: None})()
        _mock.is_tensor = lambda x: False
        _mock.from_numpy = lambda x: x

        # torch.nn stub
        _nn = types.ModuleType("torch.nn")
        _nn.Module = type("Module", (), {"__module__": "torch.nn"})
        _mock.nn = _nn

        # torch.cuda stub
        _cuda = types.ModuleType("torch.cuda")
        _cuda.is_available = lambda: False
        _mock.cuda = _cuda

        # torch.distributed stub (needed by modelscope)
        _dist = types.ModuleType("torch.distributed")
        _dist.is_initialized = lambda: False
        _dist.is_available = lambda: False
        _mock.distributed = _dist

        # Register in sys.modules
        sys.modules["torch"] = _mock
        sys.modules["torch.nn"] = _nn
        sys.modules["torch.cuda"] = _cuda
        sys.modules["torch.distributed"] = _dist

        # Also stub torch.nn.functional
        _nnf = types.ModuleType("torch.nn.functional")
        sys.modules["torch.nn.functional"] = _nnf
        _nn.functional = _nnf


_ensure_torch_mock()


def create_ocr(lang: str = "hi", use_gpu: bool = True):
    """
    Create and configure a PaddleOCR instance.

    Args:
        lang: OCR language model ('hi' for Hindi, also handles English).
        use_gpu: Whether to use GPU acceleration.

    Returns:
        Configured PaddleOCR instance.
    """
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(
        lang=lang,
        use_angle_cls=True,       # Detect and correct rotated text
        use_gpu=use_gpu,          # Use NVIDIA GPU for acceleration
        show_log=False,           # Suppress verbose logs
        # Detection tuning for small dictionary text:
        det_db_thresh=0.3,        # Lower threshold → catch smaller text
        det_db_box_thresh=0.5,    # Box confidence threshold
        det_db_unclip_ratio=1.8,  # Expand detection boxes slightly
        # Recognition tuning:
        rec_batch_num=16,         # Batch size for recognition
        max_text_length=100,      # Max characters per text line
    )
    return ocr


def run_ocr(image: np.ndarray, ocr_instance) -> list[dict]:
    """
    Run PaddleOCR on an image and return structured results.

    Args:
        image: Preprocessed image (grayscale or RGB numpy array).
        ocr_instance: PaddleOCR instance from create_ocr().

    Returns:
        List of dicts, each with:
            text       - str: Recognized text
            confidence - float: Confidence score (0-1)
            bbox       - list: 4 corner points [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            bbox_rect  - list: [x_min, y_min, x_max, y_max]
            center_x   - float: Center X coordinate
            center_y   - float: Center Y coordinate
            height     - float: Bounding box height
            width      - float: Bounding box width
    """
    # PaddleOCR expects RGB or grayscale; if grayscale, convert to 3-channel
    if len(image.shape) == 2:
        image_for_ocr = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    else:
        image_for_ocr = image

    raw_result = ocr_instance.ocr(image_for_ocr, cls=True)

    results = []

    # Handle empty results
    if not raw_result or raw_result[0] is None:
        return results

    for line in raw_result[0]:
        bbox_points = line[0]       # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        text = line[1][0]           # Recognized text
        confidence = line[1][1]     # Confidence score (0-1)

        # Skip empty text
        if not text or not text.strip():
            continue

        # Calculate simplified bounding rect
        xs = [p[0] for p in bbox_points]
        ys = [p[1] for p in bbox_points]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)

        results.append({
            "text": text.strip(),
            "confidence": confidence,
            "bbox": bbox_points,
            "bbox_rect": [x_min, y_min, x_max, y_max],
            "center_x": (x_min + x_max) / 2,
            "center_y": (y_min + y_max) / 2,
            "height": y_max - y_min,
            "width": x_max - x_min,
        })

    # Sort by vertical position (top to bottom), then horizontal (left to right)
    results.sort(key=lambda r: (r["center_y"], r["center_x"]))

    return results


def get_confidence_stats(results: list[dict]) -> dict:
    """
    Compute confidence statistics from OCR results.

    Returns:
        dict with avg_confidence, min_confidence, low_count, unreliable_count
    """
    if not results:
        return {
            "avg_confidence": 0.0,
            "min_confidence": 0.0,
            "low_count": 0,
            "unreliable_count": 0,
            "total_count": 0,
        }

    confidences = [r["confidence"] for r in results]
    return {
        "avg_confidence": sum(confidences) / len(confidences),
        "min_confidence": min(confidences),
        "low_count": sum(1 for c in confidences if c < 0.7),
        "unreliable_count": sum(1 for c in confidences if c < 0.4),
        "total_count": len(confidences),
    }


def save_ocr_visualization(
    original_image: np.ndarray,
    ocr_results: list[dict],
    output_path: str,
):
    """
    Draw OCR bounding boxes on the original image and save.

    Green boxes = high confidence (≥ 0.7)
    Red boxes   = low confidence (< 0.7)
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Work on a copy
    vis_image = original_image.copy()

    # Convert grayscale to BGR for colored drawing
    if len(vis_image.shape) == 2:
        vis_image = cv2.cvtColor(vis_image, cv2.COLOR_GRAY2BGR)
    elif vis_image.shape[2] == 3:
        # Convert RGB to BGR for OpenCV drawing
        vis_image = cv2.cvtColor(vis_image, cv2.COLOR_RGB2BGR)

    for result in ocr_results:
        bbox = result["bbox"]
        confidence = result["confidence"]

        # Color based on confidence
        if confidence >= 0.7:
            color = (0, 255, 0)  # Green (BGR)
        else:
            color = (0, 0, 255)  # Red (BGR)

        # Draw polygon
        pts = np.array(bbox, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(vis_image, [pts], isClosed=True, color=color, thickness=2)

        # Draw text label
        x_min = int(min(p[0] for p in bbox))
        y_min = int(min(p[1] for p in bbox))
        label = f"{confidence:.2f}"
        cv2.putText(
            vis_image,
            label,
            (x_min, max(y_min - 5, 15)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            color,
            1,
        )

    cv2.imwrite(output_path, vis_image)
