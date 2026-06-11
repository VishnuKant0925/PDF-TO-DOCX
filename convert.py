"""
convert.py — Hindi Dictionary PDF → DOCX Converter

Main CLI entry point that orchestrates the full conversion pipeline:
    PDF → Render → Preprocess → OCR → Layout → Post-process → DOCX

Usage:
    python convert.py input.pdf
    python convert.py input.pdf -o output.docx --dpi 400 --pages 1-5 --debug
    python convert.py input.pdf --columns 2 --format text --verbose
"""

import argparse
import os
import sys
import time

from pipeline import renderer, preprocessor, ocr_engine, layout_analyzer, postprocessor, docx_builder


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Hindi Dictionary PDF → DOCX Converter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python convert.py dictionary.pdf
  python convert.py dictionary.pdf -o output.docx
  python convert.py dictionary.pdf --pages 1-5 --debug
  python convert.py dictionary.pdf --dpi 400 --columns 2 --verbose
        """,
    )

    parser.add_argument(
        "input",
        help="Path to the input PDF file",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output DOCX file path (default: <input>.docx)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=400,
        help="Render DPI — higher = better accuracy, slower (default: 400)",
    )
    parser.add_argument(
        "--pages",
        default="all",
        help='Page range: "all", "1-5", "1,3,7", or "1-3,7-9" (default: all)',
    )
    parser.add_argument(
        "--columns",
        type=int,
        default=None,
        choices=[1, 2, 3],
        help="Force column count (default: auto-detect)",
    )
    parser.add_argument(
        "--format",
        default="table",
        choices=["table", "text"],
        help='Output format: "table" or "text" (default: table)',
    )
    parser.add_argument(
        "--lang",
        default="hi",
        help="OCR language (default: hi — Hindi, also handles English)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save intermediate images to debug/ folder",
    )
    parser.add_argument(
        "--no-preprocess",
        action="store_true",
        help="Skip image preprocessing (use raw rendered image for OCR)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed progress and stats",
    )

    args = parser.parse_args()

    # Default output path
    if args.output is None:
        base = os.path.splitext(args.input)[0]
        args.output = base + ".docx"

    return args


def parse_pages(page_spec: str, total_pages: int) -> list[int]:
    """
    Parse page specification string into 0-indexed page numbers.

    Examples:
        'all'     → [0, 1, ..., total-1]
        '1-5'     → [0, 1, 2, 3, 4]
        '1,3,7'   → [0, 2, 6]
        '1-3,7-9' → [0, 1, 2, 6, 7, 8]
    """
    if page_spec.strip().lower() == "all":
        return list(range(total_pages))

    pages = set()
    parts = page_spec.split(",")

    for part in parts:
        part = part.strip()
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                start = int(start.strip())
                end = int(end.strip())
                for p in range(start, end + 1):
                    if 1 <= p <= total_pages:
                        pages.add(p - 1)  # Convert to 0-indexed
            except ValueError:
                print(f"  [!] Warning: Invalid page range '{part}', skipping")
        else:
            try:
                p = int(part)
                if 1 <= p <= total_pages:
                    pages.add(p - 1)  # Convert to 0-indexed
            except ValueError:
                print(f"  [!] Warning: Invalid page number '{part}', skipping")

    return sorted(pages)


def check_gpu():
    """Check if GPU is actually usable for PaddlePaddle (CUDA + cuDNN)."""
    try:
        import paddle
        if not (paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0):
            return False
        # Actually test GPU inference — catches missing cuDNN DLLs
        paddle.device.set_device("gpu:0")
        t = paddle.zeros([1], dtype="float32")
        _ = t + 1
        return True
    except Exception:
        try:
            import paddle
            paddle.device.set_device("cpu")
        except Exception:
            pass
        return False


def main():
    args = parse_arguments()

    # Validate input file
    if not os.path.isfile(args.input):
        print(f"  [ERROR] File not found: {args.input}")
        sys.exit(1)

    if not args.input.lower().endswith(".pdf"):
        print(f"  [!] Warning: File does not have .pdf extension: {args.input}")

    # Banner
    print()
    print("=" * 62)
    print("   Hindi Dictionary PDF -> DOCX Converter")
    print("=" * 62)
    print()

    # Get PDF info
    total_pages = renderer.get_page_count(args.input)
    pages_to_process = parse_pages(args.pages, total_pages)

    if not pages_to_process:
        print("  [ERROR] No valid pages to process")
        sys.exit(1)

    gpu_available = check_gpu()

    print(f"  Input:      {args.input}")
    print(f"  Output:     {args.output}")
    print(f"  Pages:      {len(pages_to_process)} of {total_pages}", end="")
    if args.pages != "all":
        display_pages = [p + 1 for p in pages_to_process]
        print(f" (pages {display_pages})", end="")
    print()
    print(f"  DPI:        {args.dpi}")
    print(f"  GPU:        {'Yes' if gpu_available else 'No (CPU mode)'}")
    print(f"  Format:     {args.format}")
    print(f"  Debug:      {'On' if args.debug else 'Off'}")
    print()

    # Create debug directory
    if args.debug:
        os.makedirs("debug", exist_ok=True)

    # Step 1: Initialize OCR engine
    print("  [1/2] Initializing PaddleOCR...", end="", flush=True)
    start_init = time.time()
    ocr = ocr_engine.create_ocr(lang=args.lang, use_gpu=gpu_available)
    init_time = time.time() - start_init
    print(f" OK ({init_time:.1f}s)")
    print()

    # Step 2: Process pages
    print("  [2/2] Processing pages...")
    print()

    all_pages = []
    total_entries = 0
    all_confidences = []
    start_process = time.time()

    for i, page_num in enumerate(pages_to_process):
        page_start = time.time()
        progress = f"  Page {i+1}/{len(pages_to_process)} (PDF page {page_num + 1})"
        print(f"  {progress}")

        # Render
        if args.verbose:
            print(f"    -> Rendering at {args.dpi} DPI...", end="", flush=True)
        page_img = renderer.render_page(args.input, page_num, dpi=args.dpi)
        if args.debug:
            renderer.save_debug_image(
                page_img["image_np"],
                f"debug/page_{page_num + 1:03d}_raw.png",
            )
        if args.verbose:
            print(f" ({page_img['width_px']}x{page_img['height_px']}px)")

        # Preprocess
        if args.no_preprocess:
            processed_img = page_img["image_np"]
        else:
            if args.verbose:
                print("    -> Preprocessing...", end="", flush=True)
            debug_path = f"debug/page_{page_num + 1:03d}" if args.debug else None
            processed_img = preprocessor.preprocess(
                page_img["image_np"],
                debug_path=debug_path,
            )
            if args.verbose:
                print(" OK")

        # OCR
        if args.verbose:
            print("    -> Running OCR...", end="", flush=True)
        ocr_results = ocr_engine.run_ocr(processed_img, ocr)
        if args.debug:
            ocr_engine.save_ocr_visualization(
                page_img["image_np"],
                ocr_results,
                f"debug/page_{page_num + 1:03d}_ocr_boxes.png",
            )
        if args.verbose:
            stats = ocr_engine.get_confidence_stats(ocr_results)
            print(
                f" {stats['total_count']} text regions"
                f" (avg conf: {stats['avg_confidence']:.0%},"
                f" low: {stats['low_count']})"
            )

        # Layout analysis
        if args.verbose:
            print("    -> Analyzing layout...", end="", flush=True)
        header, columns = layout_analyzer.analyze(
            ocr_results,
            page_img["width_px"],
            page_img["height_px"],
            forced_columns=args.columns,
        )
        if args.verbose:
            print(f" {len(columns)} column(s)")

        # Post-process
        if args.verbose:
            print("    -> Post-processing...", end="", flush=True)
        page_data = postprocessor.process(header, columns, page_num)
        if args.verbose:
            print(f" {page_data['stats']['total_entries']} entries")

        all_pages.append(page_data)

        # Accumulate stats
        n_entries = page_data["stats"]["total_entries"]
        total_entries += n_entries
        avg_conf = page_data["stats"]["avg_confidence"]
        all_confidences.append(avg_conf)

        page_time = time.time() - page_start
        print(
            f"    [OK] {n_entries} entries extracted"
            f" | confidence: {avg_conf:.0%}"
            f" | {page_time:.1f}s"
        )

    # Build DOCX
    print()
    print("  Building DOCX...", end="", flush=True)
    docx_builder.build_docx(all_pages, args.output, mode=args.format)
    print(" OK")

    # Final summary
    process_time = time.time() - start_process
    total_time = time.time() - start_init + init_time

    file_size = os.path.getsize(args.output)
    if file_size >= 1024 * 1024:
        file_size_str = f"{file_size / (1024 * 1024):.1f} MB"
    else:
        file_size_str = f"{file_size / 1024:.1f} KB"

    overall_confidence = (
        sum(all_confidences) / max(len(all_confidences), 1)
    )

    print()
    print("=" * 62)
    print("   [OK] Conversion Complete!")
    print("=" * 62)
    print()
    print(f"  Output:          {args.output}")
    print(f"  File size:       {file_size_str}")
    print(f"  Pages processed: {len(pages_to_process)}")
    print(f"  Total entries:   {total_entries}")
    print(f"  Avg confidence:  {overall_confidence:.1%}")
    print(f"  Processing time: {process_time:.1f}s")
    if args.debug:
        print(f"  Debug images:    debug/")
    print()


if __name__ == "__main__":
    main()
