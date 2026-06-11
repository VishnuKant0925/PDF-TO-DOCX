"""
Hindi Dictionary PDF → DOCX Converter Pipeline

Modules:
    renderer        - PDF page → high-res image (PyMuPDF)
    preprocessor    - Image cleanup for OCR (OpenCV)
    ocr_engine      - PaddleOCR wrapper for Hindi + English
    layout_analyzer - Column detection & reading order
    postprocessor   - Text cleanup & entry structure detection
    docx_builder    - DOCX file construction (python-docx)
"""

from . import renderer
from . import preprocessor
from . import ocr_engine
from . import layout_analyzer
from . import postprocessor
from . import docx_builder

__all__ = [
    "renderer",
    "preprocessor",
    "ocr_engine",
    "layout_analyzer",
    "postprocessor",
    "docx_builder",
]
