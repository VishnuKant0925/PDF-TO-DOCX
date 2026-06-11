"""
postprocessor.py — Text Cleanup & Entry Structure Detection

Cleans up raw OCR output and detects the 3-field dictionary entry
structure: English term | Subject codes | Hindi translation.

Processing steps:
    1. Unicode normalization (NFC for Devanagari)
    2. Fix Hindi spacing (remove spaces within words)
    3. Remove duplicate/overlapping detections
    4. Detect script type (Hindi vs English)
    5. Parse dictionary entries from OCR blocks
"""

import re
import unicodedata


# Known subject abbreviation codes from the dictionary
KNOWN_SUBJECT_CODES = {
    "Mth", "Phy", "Ch", "Bot", "Env", "HS", "Gg", "Gl", "Zl",
    "Met", "Agr", "Med", "Math", "Eng", "Eco", "Geo", "Ast",
    "Bio", "Chem", "Comp", "Elec", "Min", "Opt", "Anat", "Pharm",
    "Ent", "Genet", "Micro", "Stat", "El",
}

# Common OCR misreads for subject codes
SUBJECT_CODE_FIXES = {
    "Mfh": "Mth",
    "Mih": "Mth",
    "Phy,": "Phy",
    "Ch,": "Ch",
    "Bof": "Bot",
    "Boi": "Bot",
    "H5": "HS",
    "G9": "Gg",
    "GI": "Gl",
    "ZI": "Zl",
    "Z1": "Zl",
    "2l": "Zl",
}


def process(
    header: dict,
    columns: list[dict],
    page_num: int,
) -> dict:
    """
    Process OCR results for a single page into structured entries.

    Args:
        header: Header dict from layout_analyzer.
        columns: List of column dicts from layout_analyzer.
        page_num: Page number (0-indexed).

    Returns:
        dict with page_number, header, entries list, and stats.
    """
    all_entries = []

    for column in columns:
        blocks = column.get("blocks", [])

        # Step 1-3: Clean up individual text blocks
        cleaned_blocks = []
        for block in blocks:
            cleaned = clean_text_block(block)
            if cleaned:
                cleaned_blocks.append(cleaned)

        # Step 4: Remove duplicate/overlapping detections
        deduplicated = remove_duplicates(cleaned_blocks)

        # Step 5: Parse into dictionary entries
        entries = detect_entries(deduplicated)
        all_entries.extend(entries)

    # Compute stats
    confidences = []
    for col in columns:
        for block in col.get("blocks", []):
            confidences.append(block.get("confidence", 0))

    avg_conf = sum(confidences) / max(len(confidences), 1)
    low_conf_count = sum(1 for c in confidences if c < 0.7)

    return {
        "page_number": page_num,
        "header": header,
        "entries": all_entries,
        "stats": {
            "total_entries": len(all_entries),
            "avg_confidence": avg_conf,
            "low_confidence_count": low_conf_count,
        },
    }


def clean_text_block(block: dict) -> dict | None:
    """
    Clean a single OCR text block.

    Applies: Unicode normalization, Hindi spacing fixes, subject code fixes.
    """
    text = block["text"]
    if not text or not text.strip():
        return None

    # Unicode NFC normalization — critical for Devanagari
    text = unicodedata.normalize("NFC", text)

    # Fix Hindi spacing (remove spaces within Devanagari words)
    text = fix_hindi_spacing(text)

    # Fix common OCR misreads in subject codes
    text = fix_subject_codes(text)

    # Clean up extra whitespace
    text = " ".join(text.split())

    if not text:
        return None

    result = block.copy()
    result["text"] = text
    result["script"] = detect_script(text)
    return result


def fix_hindi_spacing(text: str) -> str:
    """
    Remove incorrect spaces inserted within Devanagari words by OCR.

    Example: "शब् दकोश" → "शब्दकोश"
             "अव शोषण" → "अवशोषण"
    """
    # Remove space between two Devanagari characters
    text = re.sub(r"([\u0900-\u097F])\s+([\u0900-\u097F])", r"\1\2", text)
    # Also handle matras/vowel signs that got separated
    text = re.sub(
        r"([\u0900-\u097F])\s+([\u093E-\u094F\u0962-\u0963])", r"\1\2", text
    )
    # Handle halant (virama) separated from next consonant
    text = re.sub(r"([\u094D])\s+([\u0915-\u0939])", r"\1\2", text)
    # Run twice to catch cascading fixes
    text = re.sub(r"([\u0900-\u097F])\s+([\u0900-\u097F])", r"\1\2", text)

    return text


def fix_subject_codes(text: str) -> str:
    """Fix common OCR misreads in subject abbreviations."""
    for wrong, correct in SUBJECT_CODE_FIXES.items():
        text = text.replace(wrong, correct)
    return text


def detect_script(text: str) -> str:
    """
    Detect if text is Hindi (Devanagari), English (Latin), or mixed.

    Returns: "hindi", "english", "number", or "mixed"
    """
    devanagari_count = sum(1 for c in text if "\u0900" <= c <= "\u097F")
    latin_count = sum(1 for c in text if c.isascii() and c.isalpha())
    digit_count = sum(1 for c in text if c.isdigit())

    total_alpha = devanagari_count + latin_count

    if total_alpha == 0:
        if digit_count > 0:
            return "number"
        return "other"

    if devanagari_count > latin_count:
        return "hindi"
    elif latin_count > devanagari_count:
        return "english"
    else:
        return "mixed"


def is_subject_code(text: str) -> bool:
    """
    Check if text looks like subject abbreviation codes.

    Examples: "Phy", "Ch", "Phy, Ch", "HS, Ch, Bot"
    """
    # Clean the text
    cleaned = text.strip().rstrip(",").rstrip(".")

    # Split by comma, space, or period
    words = re.split(r"[,\s.]+", cleaned)
    words = [w.strip() for w in words if w.strip()]

    if not words:
        return False

    # Check if all words are known codes or look like abbreviations
    # (short capitalized words, ≤ 5 chars)
    matches = 0
    for w in words:
        if w in KNOWN_SUBJECT_CODES:
            matches += 1
        elif len(w) <= 5 and w[0].isupper() and w.isalpha():
            matches += 1

    # At least 50% of words should match
    return matches >= len(words) * 0.5


def is_at_column_left_edge(block: dict, all_blocks: list[dict]) -> bool:
    """
    Check if a block is at the leftmost position of its column.

    Uses the leftmost 30% of the column's X-range as the "left edge".
    """
    if not all_blocks:
        return True

    # Find the column's left and right bounds
    x_positions = [b["bbox_rect"][0] for b in all_blocks]
    col_left = min(x_positions)
    col_right = max(b["bbox_rect"][2] for b in all_blocks)
    col_width = col_right - col_left

    if col_width <= 0:
        return True

    # Block is "at left edge" if its left edge is within the first 35%
    block_left = block["bbox_rect"][0]
    return (block_left - col_left) < col_width * 0.35


def remove_duplicates(
    blocks: list[dict], iou_threshold: float = 0.5
) -> list[dict]:
    """
    Remove overlapping detections, keeping the one with higher confidence.

    Two blocks are considered duplicates if their IoU exceeds the threshold.
    """
    if not blocks:
        return []

    # Sort by confidence (highest first)
    sorted_blocks = sorted(blocks, key=lambda b: b["confidence"], reverse=True)
    kept = []

    for block in sorted_blocks:
        is_duplicate = False
        for existing in kept:
            if _compute_iou(block["bbox_rect"], existing["bbox_rect"]) > iou_threshold:
                is_duplicate = True
                break
        if not is_duplicate:
            kept.append(block)

    # Re-sort by position (top to bottom)
    kept.sort(key=lambda r: (r["center_y"], r["center_x"]))
    return kept


def _compute_iou(rect1: list, rect2: list) -> float:
    """Compute Intersection over Union of two rectangles [x_min, y_min, x_max, y_max]."""
    x1 = max(rect1[0], rect2[0])
    y1 = max(rect1[1], rect2[1])
    x2 = min(rect1[2], rect2[2])
    y2 = min(rect1[3], rect2[3])

    if x1 >= x2 or y1 >= y2:
        return 0.0

    intersection = (x2 - x1) * (y2 - y1)
    area1 = (rect1[2] - rect1[0]) * (rect1[3] - rect1[1])
    area2 = (rect2[2] - rect2[0]) * (rect2[3] - rect2[1])
    union = area1 + area2 - intersection

    if union <= 0:
        return 0.0

    return intersection / union


def detect_entries(column_blocks: list[dict]) -> list[dict]:
    """
    Group consecutive OCR blocks into structured dictionary entries.

    Each entry has:
        english_term       - str (the headword)
        subject_codes      - str (e.g., "Phy, Ch")
        hindi_translation  - str (Devanagari text)
        notes              - str (parenthetical, e.g., "(= transmission curve)")
        confidence_avg     - float

    Algorithm:
        - New entry starts when we see an English word at the column's left edge
          that is NOT a subject code.
        - Subject codes, Hindi text, and notes are attached to the current entry.
        - Multi-line entries are merged (rows without a new headword).
    """
    entries = []
    current_entry = None
    confidences = []

    for block in column_blocks:
        text = block["text"].strip()
        script = block.get("script", detect_script(text))
        confidence = block.get("confidence", 0)

        # Determine if this starts a new entry
        is_new_headword = (
            script == "english"
            and is_at_column_left_edge(block, column_blocks)
            and not is_subject_code(text)
            and not text.startswith("(")
            and not text.startswith("=")
        )

        if is_new_headword:
            # Save previous entry
            if current_entry:
                current_entry["confidence_avg"] = (
                    sum(confidences) / max(len(confidences), 1)
                )
                entries.append(current_entry)

            # Start new entry
            current_entry = {
                "english_term": text,
                "subject_codes": "",
                "hindi_translation": "",
                "notes": "",
                "confidence_avg": 0.0,
            }
            confidences = [confidence]

        elif current_entry is not None:
            confidences.append(confidence)

            if script == "hindi":
                # Append Hindi translation
                if current_entry["hindi_translation"]:
                    current_entry["hindi_translation"] += ", " + text
                else:
                    current_entry["hindi_translation"] = text

            elif is_subject_code(text):
                # Append subject codes
                cleaned_code = text.strip().rstrip(",")
                if current_entry["subject_codes"]:
                    current_entry["subject_codes"] += ", " + cleaned_code
                else:
                    current_entry["subject_codes"] = cleaned_code

            elif text.startswith("(") or text.startswith("="):
                # Parenthetical note
                if current_entry["notes"]:
                    current_entry["notes"] += " " + text
                else:
                    current_entry["notes"] = text

            elif script == "english":
                # Continuation of multi-word English term or subject code
                # on the same line as the headword
                if not current_entry["subject_codes"] and not current_entry["hindi_translation"]:
                    # Still building the English term
                    current_entry["english_term"] += " " + text
                else:
                    # Probably a continuation subject code or note
                    if len(text) <= 5 and text[0].isupper():
                        if current_entry["subject_codes"]:
                            current_entry["subject_codes"] += ", " + text
                        else:
                            current_entry["subject_codes"] = text
                    else:
                        current_entry["english_term"] += " " + text

            elif script == "number":
                # Could be a numbered translation prefix like "1." or "2."
                pass  # Numbers are usually part of other text blocks

        else:
            # No current entry yet — skip orphaned blocks
            pass

    # Don't forget the last entry
    if current_entry:
        current_entry["confidence_avg"] = (
            sum(confidences) / max(len(confidences), 1)
        )
        entries.append(current_entry)

    return entries
