# Hindi Dictionary PDF → DOCX Converter

A command-line tool to convert Hindi scientific/technical dictionary PDFs into editable DOCX files using OCR. Bypasses broken PDF font encodings by rendering pages as images and reading them with PaddleOCR.

## Features

- **OCR-based conversion** — reads rendered pixels, bypasses broken Unicode mapping
- **Hindi + English support** — PaddleOCR's Hindi model handles both scripts
- **2-column layout detection** — automatically splits dictionary columns
- **Structured output** — 3-column Word table (English term | Subject | Hindi translation)
- **GPU acceleration** — uses NVIDIA CUDA for ~5-10x faster processing
- **Debug mode** — saves preprocessed images and OCR bounding box visualizations

## Installation

### Prerequisites
- Python 3.10+
- NVIDIA GPU with CUDA toolkit (recommended, not required)

### Install dependencies

```bash
# With GPU support (recommended if you have NVIDIA GPU):
pip install paddlepaddle-gpu paddleocr pymupdf python-docx opencv-python numpy Pillow

# CPU only (slower but works everywhere):
pip install paddlepaddle paddleocr pymupdf python-docx opencv-python numpy Pillow
```

> **Note:** First install downloads ~1GB+ (PaddlePaddle + PaddleOCR Hindi model). Subsequent runs are instant.

## Usage

### Basic conversion
```bash
python convert.py dictionary.pdf
```

### With options
```bash
# Specify output path
python convert.py dictionary.pdf -o output.docx

# Convert specific pages only
python convert.py dictionary.pdf --pages 1-5

# Enable debug mode (saves intermediate images)
python convert.py dictionary.pdf --debug

# Force 2-column layout
python convert.py dictionary.pdf --columns 2

# Text output format (paragraphs instead of tables)
python convert.py dictionary.pdf --format text

# Full options
python convert.py dictionary.pdf -o output.docx --dpi 400 --pages 1-10 --debug --verbose
```

### CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `input` | Required | Path to input PDF file |
| `-o, --output` | `<input>.docx` | Output DOCX file path |
| `--dpi` | `400` | Render DPI (higher = better accuracy, slower) |
| `--pages` | `all` | Page range: `1-5`, `1,3,7`, or `all` |
| `--columns` | Auto | Force column count: 1, 2, or 3 |
| `--format` | `table` | Output format: `table` or `text` |
| `--lang` | `hi` | OCR language |
| `--debug` | Off | Save intermediate images to `debug/` |
| `--no-preprocess` | Off | Skip image preprocessing |
| `--verbose` | Off | Print detailed progress |

## Output Format

### Table Mode (default)
Each page's dictionary entries are presented in a 3-column Word table:

| English Term | Subject | Hindi Translation |
|-------------|---------|-------------------|
| **absorption** | *Phy, Ch* | अवशोषण |
| **absorptance** | *Phy, Ch* | अवशोषणांश |

### Text Mode
Each entry is a formatted paragraph:
> **absorption** *[Phy, Ch]* — अवशोषण

## Debug Mode

When `--debug` is enabled, the following files are saved to `debug/`:

| File | Content |
|------|---------|
| `page_NNN_raw.png` | Raw rendered PDF page |
| `page_NNN/01_gray.png` | After grayscale conversion |
| `page_NNN/02_clahe.png` | After contrast enhancement |
| `page_NNN/03_threshold.png` | After binarization |
| `page_NNN/04_denoise.png` | After noise removal |
| `page_NNN/05_deskew.png` | After rotation correction |
| `page_NNN/06_cropped.png` | After border cropping |
| `page_NNN/preprocessed.png` | Final preprocessed image |
| `page_NNN_ocr_boxes.png` | OCR bounding boxes visualization |

## Project Structure

```
├── convert.py              # Main CLI entry point
├── pipeline/
│   ├── __init__.py         # Package init
│   ├── renderer.py         # PDF → high-res image
│   ├── preprocessor.py     # Image cleanup for OCR
│   ├── ocr_engine.py       # PaddleOCR wrapper
│   ├── layout_analyzer.py  # Column detection & reading order
│   ├── postprocessor.py    # Text cleanup & entry structure detection
│   └── docx_builder.py     # DOCX file construction
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `paddlepaddle-gpu` install fails | Install CPU version: `pip install paddlepaddle` |
| OCR accuracy is low | Try higher DPI: `--dpi 500` |
| Columns detected incorrectly | Force column count: `--columns 2` |
| Hindi text has broken spacing | This is handled automatically by post-processing |
| First run is slow | PaddleOCR downloads models on first use (~200MB) |
