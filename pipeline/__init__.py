"""
Hindi Dictionary PDF → DOCX Converter Pipeline

Modules:
    renderer        - PDF page → high-res image (PyMuPDF)
    preprocessor    - Image cleanup for OCR (OpenCV)
    ocr_engine      - PaddleOCR wrapper (legacy)
    ocr_surya       - Surya OCR wrapper (primary — PyTorch + CUDA)
    layout_analyzer - Column detection & reading order
    postprocessor   - Text cleanup & entry structure detection
    docx_builder    - DOCX file construction (python-docx)
"""

from . import renderer
from . import preprocessor
from . import layout_analyzer
from . import postprocessor
from . import docx_builder

# Import OCR engines conditionally — only the one in use needs to load
try:
    from . import ocr_surya
except ImportError as e:
    import warnings
    warnings.warn(f"Could not import ocr_surya: {e}")
    ocr_surya = None
except Exception as e:
    # Don't silently swallow non-ImportError exceptions (e.g. CUDA errors)
    import warnings
    warnings.warn(f"ocr_surya import failed with unexpected error: {e}")
    raise

try:
    from . import ocr_engine
except ImportError:
    ocr_engine = None

__all__ = [
    "renderer",
    "preprocessor",
    "ocr_engine",
    "ocr_surya",
    "layout_analyzer",
    "postprocessor",
    "docx_builder",
]
