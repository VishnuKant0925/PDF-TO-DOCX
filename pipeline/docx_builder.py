"""
docx_builder.py — DOCX Construction

Builds a well-formatted, editable DOCX file from structured dictionary entries.
Supports two output modes:
    - Table mode (default): 3-column Word table per page
    - Text mode: Paragraph-based format

Uses python-docx for document generation.
"""

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml


def build_docx(
    all_pages: list[dict],
    output_path: str,
    mode: str = "table",
):
    """
    Build a DOCX file from processed page data.

    Args:
        all_pages: List of page dicts from postprocessor.
        output_path: Path for the output DOCX file.
        mode: "table" (default) or "text".
    """
    doc = Document()

    # Page setup: A4, reasonable margins
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)
    section.top_margin = Cm(1.5)
    section.bottom_margin = Cm(1.5)

    # Set default font
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Arial"
    font.size = Pt(10)

    for page_idx, page_data in enumerate(all_pages):
        if page_idx > 0:
            doc.add_page_break()

        # Page header
        header = page_data.get("header", {})
        _add_page_header(doc, header)

        # Entries
        entries = page_data.get("entries", [])
        if not entries:
            doc.add_paragraph("[No entries detected on this page]")
            continue

        if mode == "table":
            _add_entries_as_table(doc, entries)
        else:
            _add_entries_as_text(doc, entries)

    doc.save(output_path)


def _add_page_header(doc: Document, header: dict):
    """Add the page header (guide words + page number)."""
    left = header.get("left_word", "")
    page_num = header.get("page_number", "")
    right = header.get("right_word", "")

    if not any([left, page_num, right]):
        return

    header_text = ""
    if left:
        header_text += left
    if page_num:
        if header_text:
            header_text += "    —    "
        header_text += page_num
    if right:
        if header_text:
            header_text += "    —    "
        header_text += right

    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = para.add_run(header_text)
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(100, 100, 100)
    run.italic = True

    # Add a thin horizontal rule
    rule_para = doc.add_paragraph()
    rule_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rule_run = rule_para.add_run("─" * 90)
    rule_run.font.size = Pt(4)
    rule_run.font.color.rgb = RGBColor(180, 180, 180)

    # Reduce spacing after header
    para.paragraph_format.space_after = Pt(2)
    rule_para.paragraph_format.space_after = Pt(6)


def _add_entries_as_table(doc: Document, entries: list[dict]):
    """
    Add entries as a 3-column Word table.

    Columns: English Term | Subject Codes | Hindi Translation
    """
    # Create table with header row
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
        run.font.name = "Arial"
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
        run_en.font.name = "Arial"
        run_en.font.size = Pt(10)

        # Add notes below the English term if present
        notes = entry.get("notes", "")
        if notes:
            run_note = para_en.add_run(f"\n{notes}")
            run_note.font.size = Pt(8)
            run_note.font.color.rgb = RGBColor(100, 100, 100)
            run_note.italic = True

        # Column 2: Subject codes (italic)
        cell_sub = row.cells[1]
        para_sub = cell_sub.paragraphs[0]
        run_sub = para_sub.add_run(entry.get("subject_codes", ""))
        run_sub.italic = True
        run_sub.font.name = "Arial"
        run_sub.font.size = Pt(9)
        run_sub.font.color.rgb = RGBColor(80, 80, 80)
        para_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Column 3: Hindi translation
        cell_hi = row.cells[2]
        para_hi = cell_hi.paragraphs[0]
        hindi_text = entry.get("hindi_translation", "")
        run_hi = para_hi.add_run(hindi_text)
        run_hi.font.name = "Mangal"
        run_hi.font.size = Pt(10)

        # Alternate row shading for readability
        if entry_idx % 2 == 0:
            for cell in row.cells:
                _set_cell_shading(cell, "F8F9FA")


def _add_entries_as_text(doc: Document, entries: list[dict]):
    """
    Add entries as formatted paragraphs.

    Format: **English term** *Subject codes* — Hindi translation
    """
    for entry in entries:
        para = doc.add_paragraph()

        # English term (bold)
        run_en = para.add_run(entry.get("english_term", ""))
        run_en.bold = True
        run_en.font.name = "Arial"
        run_en.font.size = Pt(10)

        # Subject codes (italic, gray)
        subject = entry.get("subject_codes", "")
        if subject:
            run_sub = para.add_run(f"  [{subject}]")
            run_sub.italic = True
            run_sub.font.name = "Arial"
            run_sub.font.size = Pt(9)
            run_sub.font.color.rgb = RGBColor(100, 100, 100)

        # Hindi translation
        hindi = entry.get("hindi_translation", "")
        if hindi:
            run_sep = para.add_run("  —  ")
            run_sep.font.color.rgb = RGBColor(150, 150, 150)

            run_hi = para.add_run(hindi)
            run_hi.font.name = "Mangal"
            run_hi.font.size = Pt(10)

        # Notes
        notes = entry.get("notes", "")
        if notes:
            run_note = para.add_run(f"  {notes}")
            run_note.font.size = Pt(8)
            run_note.font.color.rgb = RGBColor(100, 100, 100)
            run_note.italic = True

        # Compact spacing
        para.paragraph_format.space_before = Pt(1)
        para.paragraph_format.space_after = Pt(1)


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
