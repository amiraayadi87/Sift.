"""Render a CV written in simple markdown into a clean one-page A4 PDF.

Usage: python cv_pdf.py <cv.md> <out.pdf>

Markdown accepted:
  # Name                      -> large name
  first paragraph after name  -> contact line
  ## Section                  -> section heading with a rule
  ### Left · more >> Right    -> entry heading: left part bold, text after " · " normal,
                                 text after " >> " right-aligned (dates)
  #### Text                   -> italic line (job title under the company)
  - bullet                    -> bullet point
  plain lines                 -> paragraphs
Inline: **bold**, [text](url)
The script shrinks the font size step by step until the CV fits on one page.
"""
import re
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, KeepTogether, ListFlowable, ListItem,
                                Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

NAVY = colors.black  # clean black-and-white PM style (28 Oct 2026)
GREY = colors.HexColor("#333333")
RULE = colors.black
FONT, BOLD, ITALIC = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


def inline(text):
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<link href="\2" color="#1F3A5F">\1</link>', text)
    return text


def styles(size):
    lead = size * 1.32
    return {
        "name": ParagraphStyle("name", fontName=BOLD, fontSize=size * 2.3, leading=size * 2.6,
                               textColor=NAVY, spaceAfter=size * 0.2, alignment=TA_CENTER),
        "contact": ParagraphStyle("contact", fontName=FONT, fontSize=size * 0.95, leading=lead,
                                  textColor=GREY, spaceAfter=size * 0.4, alignment=TA_CENTER),
        "h2": ParagraphStyle("h2", fontName=BOLD, fontSize=size * 1.12, leading=size * 1.4,
                             textColor=NAVY, spaceBefore=size * 0.6, spaceAfter=size * 0.1),
        "h3": ParagraphStyle("h3", fontName=BOLD, fontSize=size, leading=lead,
                             spaceBefore=size * 0.25, spaceAfter=size * 0.05),
        "h3r": ParagraphStyle("h3r", fontName=FONT, fontSize=size, leading=lead, alignment=TA_RIGHT),
        "h4": ParagraphStyle("h4", fontName=ITALIC, fontSize=size, leading=lead, spaceAfter=size * 0.1),
        "body": ParagraphStyle("body", fontName=FONT, fontSize=size, leading=lead,
                               alignment=TA_LEFT, spaceAfter=size * 0.2),
        "bullet": ParagraphStyle("bullet", fontName=FONT, fontSize=size, leading=lead, spaceAfter=size * 0.05),
    }


def build(md, size):
    st = styles(size)
    story, bullets = [], []
    seen_name = contact_done = False

    def flush():
        if bullets:
            story.append(ListFlowable(
                [ListItem(Paragraph(inline(b), st["bullet"]), leftIndent=size * 1.1,
                          value="•") for b in bullets],
                bulletType="bullet", start="•", bulletFontName=FONT, bulletFontSize=size * 0.9,
                leftIndent=size * 1.1, bulletOffsetY=-0.5, spaceAfter=size * 0.15))
            bullets.clear()

    for raw in md.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("- "):
            bullets.append(line[2:])
            continue
        flush()
        if line.startswith("# "):
            story.append(Paragraph(inline(line[2:]), st["name"]))
            seen_name = True
        elif line.startswith("## "):
            story.append(KeepTogether([
                Paragraph(inline(line[3:]).upper(), st["h2"]),
                HRFlowable(width="100%", thickness=0.6, color=RULE, spaceBefore=0,
                           spaceAfter=size * 0.3)]))
        elif line.startswith("#### "):
            story.append(Paragraph(inline(line[5:]), st["h4"]))
        elif line.startswith("### "):
            body, _, right = line[4:].partition(" >> ")
            parts = body.split(" · ", 1)
            text = "<b>%s</b>" % inline(parts[0])
            if len(parts) > 1:
                text += ' | <font name="%s">%s</font>' % (FONT, inline(parts[1]))
            if right:
                width = A4[0] - 30 * mm
                t = Table([[Paragraph(text, st["h3"]), Paragraph(inline(right), st["h3r"])]],
                          colWidths=[width * 0.72, width * 0.28])
                t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                       ("TOPPADDING", (0, 0), (-1, -1), size * 0.25), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
                story.append(t)
            else:
                story.append(Paragraph(text, st["h3"]))
        elif seen_name and not contact_done:
            story.append(Paragraph(inline(line), st["contact"]))
            story.append(HRFlowable(width="100%", thickness=1.0, color=NAVY, spaceAfter=size * 0.2))
            contact_done = True
        else:
            story.append(Paragraph(inline(line), st["body"]))
    flush()
    return story


def render(md_path, out_path):
    md = open(md_path, encoding="utf-8").read()
    for size in [10.5, 10.25, 10, 9.75, 9.5, 9.25, 9, 8.75, 8.5, 8.25, 8]:
        pages = []
        doc = SimpleDocTemplate(out_path, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                                topMargin=11 * mm, bottomMargin=10 * mm,
                                title="CV", author=md.splitlines()[0].lstrip("# ").strip())
        doc.build(build(md, size), onLaterPages=lambda c, d: pages.append(d.page),
                  onFirstPage=lambda c, d: pages.append(d.page))
        if len(pages) <= 1:
            return size, 1
    return size, len(pages)


if __name__ == "__main__":
    size, n = render(sys.argv[1], sys.argv[2])
    print("font %.2fpt, %d page(s)" % (size, n))
