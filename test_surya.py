"""
test_surya.py - Surya OCR v0.6.x Validation on Page 1

Standalone test to verify Surya OCR works correctly on the sample dictionary PDF
before any pipeline refactoring. This is the critical validation gate.

Usage:
    venv\\Scripts\\python.exe test_surya.py
"""

import os
import sys
import time
import json
import numpy as np
from PIL import Image, ImageDraw

# Fix Windows console encoding for Hindi/Devanagari text
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ── Step 0: Imports ──────────────────────────────────────────────────────────

print("=" * 62)
print("   Surya OCR v0.6 Validation - Page 1 Test")
print("=" * 62)
print()

print("  [1/5] Loading libraries...", end="", flush=True)
t0 = time.time()

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf

import torch
print(f" torch OK (CUDA={torch.cuda.is_available()})", end="", flush=True)

# Surya v0.6.x high-level OCR API
from surya.ocr import run_ocr
from surya.model.detection.model import load_model as load_det_model, load_processor as load_det_processor
from surya.model.recognition.model import load_model as load_rec_model
from surya.model.recognition.processor import load_processor as load_rec_processor

print(f" surya OK ({time.time()-t0:.1f}s)")

# ── Step 1: Render page ──────────────────────────────────────────────────────

PDF_PATH = "sample_dictionary.pdf"
PAGE_NUM = 0  # 0-indexed (page 1)
DPI = 400
DEBUG_DIR = "debug/surya_test"

os.makedirs(DEBUG_DIR, exist_ok=True)

print(f"  [2/5] Rendering page 1 at {DPI} DPI...", end="", flush=True)
t1 = time.time()

doc = pymupdf.open(PDF_PATH)
page = doc[PAGE_NUM]
zoom = DPI / 72.0
matrix = pymupdf.Matrix(zoom, zoom)
pixmap = page.get_pixmap(matrix=matrix, alpha=False)

image_np = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
    pixmap.height, pixmap.width, 3
).copy()

image_pil = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

page_width_pt = page.rect.width
page_height_pt = page.rect.height
doc.close()

print(f" {pixmap.width}x{pixmap.height}px, page={page_width_pt:.0f}x{page_height_pt:.0f}pt ({time.time()-t1:.1f}s)")

image_pil.save(os.path.join(DEBUG_DIR, "page1_raw.png"))

# ── Step 2: Load models ─────────────────────────────────────────────────────

print("  [3/5] Loading Surya models...", end="", flush=True)
t2 = time.time()

det_model = load_det_model()
det_processor = load_det_processor()
rec_model = load_rec_model()
rec_processor = load_rec_processor()

print(f" OK ({time.time()-t2:.1f}s)")

# ── Step 3: Run OCR (detection + recognition) ───────────────────────────────

print("  [4/5] Running OCR (detection + recognition)...", end="", flush=True)
t3 = time.time()

# run_ocr: high-level API that handles detection + recognition in one call
# Args: images, languages_per_image, det_model, det_processor, rec_model, rec_processor
predictions = run_ocr(
    [image_pil],              # list of images
    [["en", "hi"]],           # languages per image
    det_model,
    det_processor,
    rec_model,
    rec_processor,
)

ocr_result = predictions[0]
n_lines = len(ocr_result.text_lines)
print(f" {n_lines} lines ({time.time()-t3:.1f}s)")

# ── Step 4: Collect and display results ──────────────────────────────────────

print("  [5/5] Processing results...")
print()

all_results = []
for i, text_line in enumerate(ocr_result.text_lines):
    text = text_line.text
    confidence = text_line.confidence
    bbox = text_line.bbox  # [x1, y1, x2, y2]

    all_results.append({
        "index": i,
        "text": text,
        "confidence": confidence,
        "bbox": bbox,
        "center_x": (bbox[0] + bbox[2]) / 2,
        "center_y": (bbox[1] + bbox[3]) / 2,
        "width": bbox[2] - bbox[0],
        "height": bbox[3] - bbox[1],
    })

# Sort by reading order (top to bottom, left to right)
all_results.sort(key=lambda r: (r["center_y"], r["center_x"]))

# Determine column split (midpoint of image)
mid_x = pixmap.width / 2

left_col = [r for r in all_results if r["center_x"] < mid_x]
right_col = [r for r in all_results if r["center_x"] >= mid_x]

print("  -- LEFT COLUMN --")
for r in left_col:
    conf_str = f"{r['confidence']:.2f}"
    print(f"    [{r['index']:3d}] ({conf_str}) {r['text']}")

print()
print("  -- RIGHT COLUMN --")
for r in right_col:
    conf_str = f"{r['confidence']:.2f}"
    print(f"    [{r['index']:3d}] ({conf_str}) {r['text']}")

# ── Save visualizations ─────────────────────────────────────────────────────

print()
print("  Saving visualizations...", end="", flush=True)

# OCR bounding boxes
vis_image = image_pil.copy()
draw = ImageDraw.Draw(vis_image)

for r in all_results:
    x1, y1, x2, y2 = r["bbox"]
    color = "green" if r["confidence"] >= 0.7 else "red"
    draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
    draw.text((x1, max(y1 - 12, 0)), f"{r['confidence']:.2f}", fill=color)

vis_image.save(os.path.join(DEBUG_DIR, "page1_ocr_boxes.png"))

# Column split visualization
vis_cols = image_pil.copy()
draw_cols = ImageDraw.Draw(vis_cols)
draw_cols.line([(mid_x, 0), (mid_x, pixmap.height)], fill="red", width=3)

for r in left_col:
    x1, y1, x2, y2 = r["bbox"]
    draw_cols.rectangle([x1, y1, x2, y2], outline="blue", width=2)

for r in right_col:
    x1, y1, x2, y2 = r["bbox"]
    draw_cols.rectangle([x1, y1, x2, y2], outline="green", width=2)

vis_cols.save(os.path.join(DEBUG_DIR, "page1_columns.png"))

# Save JSON
with open(os.path.join(DEBUG_DIR, "page1_results.json"), "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

print(f" saved to {DEBUG_DIR}/")

# ── Summary ──────────────────────────────────────────────────────────────────

total_time = time.time() - t0
avg_conf = sum(r["confidence"] for r in all_results) / max(len(all_results), 1)
low_conf = sum(1 for r in all_results if r["confidence"] < 0.7)

print()
print("=" * 62)
print("   Validation Summary")
print("=" * 62)
print(f"  Total text lines:   {len(all_results)}")
print(f"  Left column lines:  {len(left_col)}")
print(f"  Right column lines: {len(right_col)}")
print(f"  Avg confidence:     {avg_conf:.1%}")
print(f"  Low confidence:     {low_conf} lines")
print(f"  Total time:         {total_time:.1f}s")
print(f"  Debug output:       {DEBUG_DIR}/")
print()

# Spot-check specific entries
print("  -- SPOT CHECKS --")
all_text = " ".join(r["text"] for r in all_results)

checks = [
    ("'absolute value' (English)", "absolute value" in all_text.lower()),
    ("'absorbable' (English)", "absorbable" in all_text.lower()),
    ("'absorb' (English)", "absorb" in all_text.lower()),
    ("'absorbent' (English)", "absorbent" in all_text.lower()),
    ("Hindi: nirpeksh", any(w in all_text for w in ["निरपेक्ष", "निरपेक्ष"])),
    ("Hindi: avshoshya", "अवशोष्य" in all_text),
    ("Subject code: Mth", "Mth" in all_text),
    ("Subject code: Phy", "Phy" in all_text),
    ("Subject code: HS", "HS" in all_text),
    ("Subject code: Bot", "Bot" in all_text),
    ("Subject code: Ch", "Ch" in all_text),
]

for label, found in checks:
    marker = "[+]" if found else "[-]"
    status = "PASS" if found else "FAIL"
    print(f"    {marker} {status}: {label}")

print()
print("  Done!")
print()
