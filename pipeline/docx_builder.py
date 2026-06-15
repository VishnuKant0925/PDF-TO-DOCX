"""
docx_builder.py — High-Fidelity DOCX Construction

Builds a DOCX file that closely matches the visual layout of the
original scanned Hindi scientific dictionary:

    - Two-column page layout using Word section columns (w:cols XML)
    - Three sub-fields per entry: English term (bold) | Subject codes (italic) | Hindi translation
    - Page header via Word's built-in header mechanism (guide words + page number)
    - Tab-stop alignment for sub-column positioning
    - Compact paragraph spacing to match dense dictionary layout
    - Matching fonts: Times New Roman for English, Mangal for Hindi
    - Column divider line (w:sep) between the two columns

Uses python-docx with low-level OxmlElement manipulation for
column support (not natively available in python-docx API).

UNIT REFERENCE (Word OOXML):
    - w:space, w:w in w:cols → twips (1 twip = 1/20 pt = 1/1440 inch)
    - python-docx Cm/Pt/Inches → EMU (English Metric Units)
    - 1 EMU = 1/914400 inch → 1 twip = 914400/1440 = 635 EMU
    - Conversion: twips = int(emu_value / 635)
"""

from docx import Document
from docx.shared import Pt, Cm, Inches, Emu, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml, OxmlElement


# ─── Fonts ────────────────────────────────────────────────────────
FONT_ENGLISH = "Times New Roman"   # Matches original serif font
FONT_HINDI = "Mangal"              # Standard Devanagari font
FONT_SUBJECT = "Times New Roman"   # Subject codes use same serif

# ─── Unit conversion ─────────────────────────────────────────────
EMU_PER_TWIP = 635  # 914400 EMU/inch ÷ 1440 twips/inch = 635


def _emu_to_twips(emu_value) -> int:
    """
    Convert an EMU value (from Cm/Pt/Inches) to twips for Word XML attributes.

    Word OOXML attributes like w:space, w:w in w:cols expect twips.
    python-docx's Cm(), Pt(), Inches() return EMU values.

    1 twip = 1/20 point = 1/1440 inch = 635 EMU
    """
    return int(int(emu_value) / EMU_PER_TWIP)


def build_docx(
    all_pages: list[dict],
    output_path: str,
    mode: str = "text",
):
    """
    Build a high-fidelity DOCX file from structured dictionary entries.

    Args:
        all_pages: List of page dicts from postprocessor.
        output_path: Path for the output DOCX file.
        mode: "text" (two-column flow) or "table" (legacy table mode).
    """
    doc = Document()

    # ── Page setup: match original dictionary dimensions ──
    section = doc.sections[0]
    section.page_width = Cm(21.0)       # A4 width
    section.page_height = Cm(29.7)      # A4 height
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)
    section.top_margin = Cm(1.5)
    section.bottom_margin = Cm(1.5)

    # ── Default paragraph style ──
    style = doc.styles["Normal"]
    style.font.name = FONT_ENGLISH
    style.font.size = Pt(9)
    pf = style.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = Pt(11)

    # ── Set East Asian / Complex Script font defaults ──
    rpr = style.element.get_or_add_rPr()
    _set_complex_script_font(rpr, FONT_HINDI)

    # ── Process each page ──
    for page_idx, page_data in enumerate(all_pages):
        if page_idx > 0:
            # Add a new section with page break for each page
            section = doc.add_section(WD_ORIENT.PORTRAIT)
            section.page_width = Cm(21.0)
            section.page_height = Cm(29.7)
            section.left_margin = Cm(1.8)
            section.right_margin = Cm(1.8)
            section.top_margin = Cm(1.5)
            section.bottom_margin = Cm(1.5)

        # Page header (guide words + page number) — using Word header
        header_data = page_data.get("header", {})
        _set_word_header(section, header_data)

        # Get entries and split into two columns
        entries = page_data.get("entries", [])
        if not entries:
            doc.add_paragraph("[No entries detected on this page]")
            continue

        # Split entries roughly in half for two-column layout
        mid = len(entries) // 2
        left_entries = entries[:mid]
        right_entries = entries[mid:]

        # Set up two-column layout for this section
        _set_section_columns(section, 2, spacing=Cm(0.8))

        if mode == "table":
            # Legacy table mode — add entries as a single full-width table
            _add_entries_as_table(doc, entries)
        else:
            # Text mode — two-column flow with tab-stop alignment
            # Add left column entries
            for entry in left_entries:
                _add_dictionary_entry(doc, entry)

            # Column break to start right column
            _add_column_break(doc)

            # Add right column entries
            for entry in right_entries:
                _add_dictionary_entry(doc, entry)

    doc.save(output_path)


def _set_word_header(section, header_data: dict):
    """
    Set the Word document header for a section.

    Format: left_guide_word     page_number     right_guide_word
    Uses a center-aligned paragraph with bold gray text.
    The header appears at the top of every page in this section.
    """
    left = header_data.get("left_word", "")
    page_num = header_data.get("page_number", "")
    right = header_data.get("right_word", "")

    if not any([left, page_num, right]):
        return

    # Access the section's header
    doc_header = section.header
    doc_header.is_linked_to_previous = False

    # Clear any existing header content
    for para in doc_header.paragraphs:
        para.clear()

    # Use the first paragraph (always exists)
    if doc_header.paragraphs:
        para = doc_header.paragraphs[0]
    else:
        para = doc_header.add_paragraph()

    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.space_before = Pt(0)
    para.paragraph_format.space_after = Pt(2)

    # Add a bottom border to the header paragraph (thin rule)
    pPr = para._element.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '4')       # 0.5pt line
    bottom.set(qn('w:space'), '1')
    bottom.set(qn('w:color'), 'C0C0C0')
    pBdr.append(bottom)
    pPr.append(pBdr)

    # Build header text: left_word — page_number — right_word
    parts = []
    if left:
        parts.append(left)
    if page_num:
        parts.append(page_num)
    if right:
        parts.append(right)

    header_text = "          ".join(parts)

    run = para.add_run(header_text)
    run.font.name = FONT_ENGLISH
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(80, 80, 80)
    run.bold = True


def _add_dictionary_entry(doc: Document, entry: dict):
    """
    Add a single dictionary entry as a compact paragraph with tab-stop alignment.

    Format: **English term**\\tSubject\\tHindi translation

    Tab stops create sub-column alignment within each Word column,
    matching the original dictionary's visual layout where each row shows:
    English term (bold) | Subject codes (italic) | Hindi translation
    """
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(1)
    para.paragraph_format.space_after = Pt(1)
    para.paragraph_format.line_spacing = Pt(11)

    # ── Set tab stops for sub-column alignment ──
    # Within each Word column (~8.5cm wide after margins and spacing),
    # position tab stops for Subject and Hindi fields.
    # Tab 1: ~5.0cm from column left edge (subject codes)
    # Tab 2: ~6.5cm from column left edge (Hindi translation)
    _add_tab_stop(para, Cm(5.0), WD_TAB_ALIGNMENT.LEFT)
    _add_tab_stop(para, Cm(6.5), WD_TAB_ALIGNMENT.LEFT)

    # ── English term (bold) ──
    english = entry.get("english_term", "").strip()
    if english:
        run_en = para.add_run(english)
        run_en.bold = True
        run_en.font.name = FONT_ENGLISH
        run_en.font.size = Pt(9)

    # ── Tab → Subject codes (italic, gray) ──
    subject = entry.get("subject_codes", "").strip()
    if subject:
        run_tab1 = para.add_run("\t")
        run_tab1.font.size = Pt(9)

        run_sub = para.add_run(subject)
        run_sub.italic = True
        run_sub.font.name = FONT_SUBJECT
        run_sub.font.size = Pt(8)
        run_sub.font.color.rgb = RGBColor(80, 80, 80)

    # ── Tab → Hindi translation ──
    hindi = entry.get("hindi_translation", "").strip()
    if hindi:
        run_tab2 = para.add_run("\t")
        run_tab2.font.size = Pt(9)

        run_hi = para.add_run(hindi)
        run_hi.font.name = FONT_HINDI
        run_hi.font.size = Pt(9)
        # Set complex script font for proper Hindi rendering
        _set_run_cs_font(run_hi, FONT_HINDI, Pt(9))

    # ── Notes (small, italic, gray) — on next line if present ──
    notes = entry.get("notes", "").strip()
    if notes:
        # Add a line break (soft return) and indent the note
        run_br = para.add_run()
        run_br.add_break()

        run_indent = para.add_run("    ")  # visual indent
        run_indent.font.size = Pt(7)

        run_note = para.add_run(notes)
        run_note.font.size = Pt(7)
        run_note.font.color.rgb = RGBColor(120, 120, 120)
        run_note.italic = True


def _add_tab_stop(para, position, alignment):
    """
    Add a tab stop to a paragraph at the given position.

    Uses low-level XML since python-docx's tab_stops API can be finicky.

    Args:
        para: The paragraph object.
        position: Position as an EMU value (e.g., Cm(5.0)).
        alignment: WD_TAB_ALIGNMENT value.
    """
    pPr = para._element.get_or_add_pPr()

    # Find or create w:tabs element
    tabs = pPr.find(qn('w:tabs'))
    if tabs is None:
        tabs = OxmlElement('w:tabs')
        pPr.append(tabs)

    tab = OxmlElement('w:tab')
    tab.set(qn('w:val'), 'left')
    # Tab position must be in twips
    tab.set(qn('w:pos'), str(_emu_to_twips(position)))
    tabs.append(tab)


def _set_section_columns(section, num_cols: int, spacing=Cm(0.6)):
    """
    Set the section to use multiple columns with proper Word XML.

    python-docx doesn't have native column support, so we
    manipulate the section's XML directly with w:cols element.

    CRITICAL: w:space expects twips, NOT EMU. python-docx's Cm/Pt
    return EMU values. We must convert: twips = EMU / 635.

    Args:
        section: The document section to modify.
        num_cols: Number of columns (1, 2, or 3).
        spacing: Inter-column spacing as a docx.shared length (e.g., Cm(0.8)).
    """
    sect_pr = section._sectPr

    # Remove existing cols element if any
    for existing_cols in sect_pr.findall(qn('w:cols')):
        sect_pr.remove(existing_cols)

    # Create new cols element
    cols = OxmlElement('w:cols')
    cols.set(qn('w:num'), str(num_cols))

    # FIXED: Convert EMU → twips for w:space attribute.
    # Before this fix, raw EMU (288000 for Cm(0.8)) was passed directly,
    # which Word interpreted as 288000 twips = 200 inches of gap,
    # collapsing all text to 1 character per line.
    spacing_twips = _emu_to_twips(spacing)
    cols.set(qn('w:space'), str(spacing_twips))

    cols.set(qn('w:equalWidth'), '1')

    # Add vertical separator line between columns
    cols.set(qn('w:sep'), '1')

    sect_pr.append(cols)


def _add_column_break(doc: Document):
    """Add a column break to move to the next column."""
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(0)
    para.paragraph_format.space_after = Pt(0)
    run = para.add_run()
    run.add_break(WD_BREAK.COLUMN)


def _set_complex_script_font(rPr, font_name: str):
    """
    Set the complex script (cs) font on an rPr element.

    This ensures Hindi/Devanagari text renders in the correct font,
    since python-docx's run.font.name only sets the Latin font.
    """
    # Remove existing rFonts if present
    for existing in rPr.findall(qn('w:rFonts')):
        rPr.remove(existing)

    rFonts = OxmlElement('w:rFonts')
    rFonts.set(qn('w:cs'), font_name)
    rFonts.set(qn('w:ascii'), FONT_ENGLISH)
    rFonts.set(qn('w:hAnsi'), FONT_ENGLISH)
    rPr.insert(0, rFonts)


def _set_run_cs_font(run, font_name: str, size=None):
    """
    Set complex script font and size on a specific run.

    This is needed because python-docx's run.font.name only
    affects Latin (w:ascii/w:hAnsi), not complex script (w:cs).
    """
    rPr = run._element.get_or_add_rPr()

    # Set cs font
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.insert(0, rFonts)
    rFonts.set(qn('w:cs'), font_name)

    # Set cs font size
    if size is not None:
        szCs = rPr.find(qn('w:szCs'))
        if szCs is None:
            szCs = OxmlElement('w:szCs')
            rPr.append(szCs)
        # Word uses half-points for sz
        szCs.set(qn('w:val'), str(int(size.pt * 2)))


# ══════════════════════════════════════════════════════════════════
# Legacy table mode (kept for backward compatibility)
# ══════════════════════════════════════════════════════════════════

def _add_entries_as_table(doc: Document, entries: list[dict]):
    """
    Add entries as a 3-column Word table (legacy mode).

    Columns: English Term | Subject Codes | Hindi Translation
    """
    from docx.enum.table import WD_TABLE_ALIGNMENT

    table = doc.add_table(rows=1, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True

    # Style the table with light borders
    _style_table(table)

    # Header row
    header_cells = table.rows[0].cells
    header_labels = ["English Term", "Subject", "Hindi Translation"]
    header_widths = [Cm(7.0), Cm(2.5), Cm(7.5)]

    for i, (label, width) in enumerate(zip(header_labels, header_widths)):
        cell = header_cells[i]
        cell.width = width
        para = cell.paragraphs[0]
        run = para.add_run(label)
        run.bold = True
        run.font.size = Pt(9)
        run.font.name = FONT_ENGLISH
        run.font.color.rgb = RGBColor(255, 255, 255)
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Dark header background
        _set_cell_shading(cell, "2C3E50")

    # Entry rows
    for entry_idx, entry in enumerate(entries):
        row = table.add_row()

        # Column 1: English term (bold)
        cell_en = row.cells[0]
        para_en = cell_en.paragraphs[0]
        run_en = para_en.add_run(entry.get("english_term", ""))
        run_en.bold = True
        run_en.font.name = FONT_ENGLISH
        run_en.font.size = Pt(9)

        # Add notes below the English term if present
        notes = entry.get("notes", "")
        if notes:
            run_note = para_en.add_run(f"\n{notes}")
            run_note.font.size = Pt(7)
            run_note.font.color.rgb = RGBColor(100, 100, 100)
            run_note.italic = True

        # Column 2: Subject codes (italic)
        cell_sub = row.cells[1]
        para_sub = cell_sub.paragraphs[0]
        run_sub = para_sub.add_run(entry.get("subject_codes", ""))
        run_sub.italic = True
        run_sub.font.name = FONT_SUBJECT
        run_sub.font.size = Pt(8)
        run_sub.font.color.rgb = RGBColor(80, 80, 80)
        para_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Column 3: Hindi translation
        cell_hi = row.cells[2]
        para_hi = cell_hi.paragraphs[0]
        hindi_text = entry.get("hindi_translation", "")
        run_hi = para_hi.add_run(hindi_text)
        run_hi.font.name = FONT_HINDI
        run_hi.font.size = Pt(9)
        _set_run_cs_font(run_hi, FONT_HINDI, Pt(9))

        # Alternate row shading for readability
        if entry_idx % 2 == 0:
            for cell in row.cells:
                _set_cell_shading(cell, "F8F9FA")


def _style_table(table):
    """Apply clean styling to the table — light borders, no outer border."""
    tbl = table._tbl
    tbl_pr = tbl.tblPr if tbl.tblPr is not None else parse_xml(
        f"<w:tblPr {nsdecls('w')}/>"
    )

    # Set table borders (thin light gray lines)
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        '  <w:top w:val="single" w:sz="4" w:space="0" w:color="D0D0D0"/>'
        '  <w:left w:val="single" w:sz="4" w:space="0" w:color="D0D0D0"/>'
        '  <w:bottom w:val="single" w:sz="4" w:space="0" w:color="D0D0D0"/>'
        '  <w:right w:val="single" w:sz="4" w:space="0" w:color="D0D0D0"/>'
        '  <w:insideH w:val="single" w:sz="2" w:space="0" w:color="E0E0E0"/>'
        '  <w:insideV w:val="single" w:sz="2" w:space="0" w:color="E0E0E0"/>'
        "</w:tblBorders>"
    )

    # Remove existing borders element if any
    for existing_borders in tbl_pr.findall(qn("w:tblBorders")):
        tbl_pr.remove(existing_borders)

    tbl_pr.append(borders)


def _set_cell_shading(cell, color_hex: str):
    """Set the background shading color of a table cell."""
    shading = parse_xml(
        f'<w:shd {nsdecls("w")} w:fill="{color_hex}" w:val="clear"/>'
    )
    cell._tc.get_or_add_tcPr().append(shading)
