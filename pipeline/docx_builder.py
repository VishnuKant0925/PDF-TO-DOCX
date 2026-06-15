"""
docx_builder.py — High-Fidelity DOCX Construction

Builds a DOCX file that closely matches the visual layout of the
original scanned Hindi scientific dictionary:

    - Two-column page layout using Word section columns (w:cols XML)
    - Three sub-fields per entry: English term (bold) | Subject codes (italic) | Hindi translation
    - Page header as centered text (guide words + page number)
    - Compact paragraph spacing to match dense dictionary layout
    - Matching fonts: Times New Roman for English, Mangal for Hindi

Uses python-docx with low-level OxmlElement manipulation for
column support (not natively available in python-docx API).
"""

from docx import Document
from docx.shared import Pt, Cm, Inches, Emu, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml, OxmlElement


# ─── Fonts ────────────────────────────────────────────────────────
FONT_ENGLISH = "Times New Roman"   # Matches original serif font
FONT_HINDI = "Mangal"              # Standard Devanagari font
FONT_SUBJECT = "Times New Roman"   # Subject codes use same serif


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

        # Page header (guide words + page number)
        header = page_data.get("header", {})
        _add_page_header(doc, header)

        # Horizontal rule under header
        _add_thin_rule(doc)

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
        _set_section_columns(doc, 2, spacing=Cm(0.8))

        # Add left column entries
        for entry in left_entries:
            _add_dictionary_entry(doc, entry)

        # Column break to start right column
        _add_column_break(doc)

        # Add right column entries
        for entry in right_entries:
            _add_dictionary_entry(doc, entry)

    doc.save(output_path)


def _add_page_header(doc: Document, header: dict):
    """
    Add the page header — guide words and page number.

    Format: "left_word        page_number        right_word"
    Centered, italic, gray text.
    """
    left = header.get("left_word", "")
    page_num = header.get("page_number", "")
    right = header.get("right_word", "")

    if not any([left, page_num, right]):
        return

    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.space_before = Pt(0)
    para.paragraph_format.space_after = Pt(2)

    # Build header: left_word — page_number — right_word
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


def _add_thin_rule(doc: Document):
    """Add a thin horizontal rule paragraph after the header."""
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.space_before = Pt(0)
    para.paragraph_format.space_after = Pt(4)

    # Use a bottom border on the paragraph instead of text characters
    pPr = para._element.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '4')       # 0.5pt line
    bottom.set(qn('w:space'), '1')
    bottom.set(qn('w:color'), 'C0C0C0')
    pBdr.append(bottom)
    pPr.append(pBdr)


def _add_dictionary_entry(doc: Document, entry: dict):
    """
    Add a single dictionary entry as a compact paragraph.

    Format: **English term**  Subject  Hindi translation

    This matches the original layout where each row shows:
    English term (bold) | Subject codes (italic) | Hindi translation
    """
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(1)
    para.paragraph_format.space_after = Pt(1)
    para.paragraph_format.line_spacing = Pt(11)

    # ── English term (bold) ──
    english = entry.get("english_term", "").strip()
    if english:
        run_en = para.add_run(english)
        run_en.bold = True
        run_en.font.name = FONT_ENGLISH
        run_en.font.size = Pt(9)

    # ── Subject codes (italic, gray) ──
    subject = entry.get("subject_codes", "").strip()
    if subject:
        run_sep = para.add_run("  ")
        run_sep.font.size = Pt(9)

        run_sub = para.add_run(subject)
        run_sub.italic = True
        run_sub.font.name = FONT_SUBJECT
        run_sub.font.size = Pt(8)
        run_sub.font.color.rgb = RGBColor(80, 80, 80)

    # ── Hindi translation ──
    hindi = entry.get("hindi_translation", "").strip()
    if hindi:
        run_sep2 = para.add_run("  ")
        run_sep2.font.size = Pt(9)

        run_hi = para.add_run(hindi)
        run_hi.font.name = FONT_HINDI
        run_hi.font.size = Pt(9)
        # Set complex script font for proper Hindi rendering
        _set_run_cs_font(run_hi, FONT_HINDI, Pt(9))

    # ── Notes (small, italic, gray) ──
    notes = entry.get("notes", "").strip()
    if notes:
        run_note = para.add_run(f"  {notes}")
        run_note.font.size = Pt(7)
        run_note.font.color.rgb = RGBColor(120, 120, 120)
        run_note.italic = True


def _set_section_columns(doc: Document, num_cols: int, spacing=Cm(0.6)):
    """
    Set the current section to use multiple columns.

    python-docx doesn't have native column support, so we
    manipulate the section's XML directly with w:cols element.
    """
    # Get the last section's sectPr
    sections = doc.sections
    last_section = sections[-1]
    sect_pr = last_section._sectPr

    # Remove existing cols element if any
    for existing_cols in sect_pr.findall(qn('w:cols')):
        sect_pr.remove(existing_cols)

    # Create new cols element
    cols = OxmlElement('w:cols')
    cols.set(qn('w:num'), str(num_cols))
    cols.set(qn('w:space'), str(int(spacing)))
    cols.set(qn('w:equalWidth'), '1')

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
