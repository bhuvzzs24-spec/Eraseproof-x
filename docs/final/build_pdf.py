"""Reproducible print report. Requires reportlab==5.1.0 and markdown-it-py==4.2.0.
Render diagrams first with render_diagrams.mjs; this script never fetches external images.
"""

import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import textwrap
from markdown_it import MarkdownIt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    NextPageTemplate,
    Image,
    Table,
    TableStyle,
    Preformatted,
    KeepTogether,
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib.utils import ImageReader

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parent.parent
BLUE = colors.HexColor("#244c8d")
INK = colors.HexColor("#17243a")
MUTED = colors.HexColor("#52657d")
PALE = colors.HexColor("#eef3fa")
LINE = colors.HexColor("#cdd8e5")
REPLACEMENTS = str.maketrans(
    {
        "\u2014": " - ",
        "\u2013": "-",
        "\u2011": "-",
        "\u2010": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u00a0": " ",
        "\u2192": "->",
        "\u2265": ">=",
        "\u2264": "<=",
        "\u00d7": "x",
    }
)


def clean(value):
    return value.translate(REPLACEMENTS)


def inline(tokens):
    output = []
    links = []
    for token in tokens or []:
        if token.type == "text":
            output.append(escape(clean(token.content)))
        elif token.type == "code_inline":
            output.append(
                '<font name="Courier" size="8.4">' + escape(clean(token.content)) + "</font>"
            )
        elif token.type == "strong_open":
            output.append("<b>")
        elif token.type == "strong_close":
            output.append("</b>")
        elif token.type == "em_open":
            output.append("<i>")
        elif token.type == "em_close":
            output.append("</i>")
        elif token.type == "link_open":
            href = token.attrGet("href") or ""
            safe = href.startswith(("https://", "http://"))
            links.append(safe)
            if safe:
                output.append('<a color="#244c8d" href="' + escape(href, quote=True) + '">')
        elif token.type == "link_close":
            if links.pop():
                output.append("</a>")
        elif token.type in ("softbreak", "hardbreak"):
            output.append(" ")
        elif token.type == "image":
            output.append(escape(clean(token.content)))
        elif token.type == "html_inline":
            output.append(escape(clean(token.content)))
    return "".join(output)


class Report(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if (
            isinstance(flowable, Paragraph)
            and flowable.style.name == "Chapter"
            and flowable.getPlainText() != "Contents"
        ):
            label = flowable.getPlainText()
            key = "chapter-" + str(self.seq.nextf("chapter"))
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(label, key, 0, False)
            self.notify("TOCEntry", (0, label, self.page, key))


def build(source, output, runtime):
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReportBody",
            fontName="Helvetica",
            fontSize=10.2,
            leading=15.3,
            textColor=INK,
            spaceAfter=8,
            splitLongWords=True,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Chapter",
            parent=styles["ReportBody"],
            fontName="Helvetica-Bold",
            fontSize=19,
            leading=24,
            textColor=BLUE,
            spaceBefore=4,
            spaceAfter=16,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Section",
            parent=styles["ReportBody"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=17,
            textColor=INK,
            spaceBefore=12,
            spaceAfter=6,
            keepWithNext=True,
        )
    )
    styles.add(ParagraphStyle(name="Minor", parent=styles["Section"], fontSize=10.4, leading=15))
    styles.add(
        ParagraphStyle(
            name="Cell",
            parent=styles["ReportBody"],
            fontSize=8,
            leading=11.2,
            spaceAfter=0,
            wordWrap="LTR",
        )
    )
    styles.add(
        ParagraphStyle(
            name="Caption",
            parent=styles["ReportBody"],
            fontSize=8.3,
            leading=11.5,
            textColor=MUTED,
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ListBody",
            parent=styles["ReportBody"],
            leftIndent=16,
            firstLineIndent=0,
            bulletIndent=2,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportCode",
            fontName="Courier",
            fontSize=7.5,
            leading=10.3,
            textColor=INK,
            backColor=PALE,
            borderPadding=9,
            spaceBefore=7,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TOC",
            fontName="Helvetica",
            fontSize=10,
            leading=18,
            leftIndent=0,
            firstLineIndent=0,
            textColor=INK,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverTitle",
            fontName="Helvetica-Bold",
            fontSize=37,
            leading=42,
            textColor=INK,
            spaceAfter=18,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverSub",
            fontName="Helvetica",
            fontSize=19,
            leading=26,
            textColor=BLUE,
            spaceAfter=20,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverSmall", parent=styles["ReportBody"], fontSize=10, leading=16, textColor=MUTED
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    document = Report(
        str(output),
        pagesize=A4,
        leftMargin=48,
        rightMargin=48,
        topMargin=54,
        bottomMargin=48,
        title="EraseProof X - Complete Technical Report",
        author="EraseProof X project",
        pageCompression=1,
    )

    def decoration(canvas, doc):
        width, height = canvas._pagesize
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(48, height - 35, width - 48, height - 35)
        canvas.setFillColor(BLUE)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(48, height - 25, "ERASEPROOF X  /  TECHNICAL REPORT")
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(
            width - 48, height - 25, "Synthetic scope - publication pending approval"
        )
        canvas.line(48, 34, width - 48, 34)
        canvas.drawString(
            48,
            22,
            "2026-11-08  |  Runtime " + runtime[:12] + "  |  Exact provenance in validation record",
        )
        canvas.drawRightString(width - 48, 22, str(doc.page))
        canvas.restoreState()

    portrait = Frame(
        48,
        48,
        A4[0] - 96,
        A4[1] - 102,
        id="portrait-frame",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    wide = landscape(A4)
    horizontal = Frame(
        48,
        48,
        wide[0] - 96,
        wide[1] - 102,
        id="landscape-frame",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    document.addPageTemplates(
        [
            PageTemplate(id="portrait", frames=[portrait], onPage=decoration, pagesize=A4),
            PageTemplate(id="landscape", frames=[horizontal], onPage=decoration, pagesize=wide),
        ]
    )
    story = [
        Spacer(1, 64),
        Paragraph("ERASEPROOF X", styles["CoverTitle"]),
        Paragraph("Complete Technical Report", styles["CoverSub"]),
        Paragraph(
            "Distributed deletion claims.<br/>Independent observations.<br/>Reproducible evidence.",
            styles["CoverSub"],
        ),
        Spacer(1, 16),
    ]
    box = Table(
        [
            [
                Paragraph(
                    "<b>PUBLIC DEPLOYMENT: PENDING OWNER APPROVAL</b><br/>No cloud resources created. No public HTTPS URL verified.<br/>A prepared stack and a green CI run are not an actual cloud deployment.",
                    styles["ReportBody"],
                )
            ]
        ],
        colWidths=[A4[0] - 96],
    )
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("BOX", (0, 0), (-1, -1), 0.8, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 15),
                ("RIGHTPADDING", (0, 0), (-1, -1), 15),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story += [
        box,
        Spacer(1, 25),
        Paragraph(
            "Phases 1-6 | 15 chapters | implementation, algorithms, measured evaluation, security, operations and interview preparation",
            styles["CoverSmall"],
        ),
        Spacer(1, 14),
        Paragraph(
            "Generated 2026-11-08<br/>Runtime source: <font name='Courier' size='8'>"
            + runtime
            + "</font><br/>Repository: https://github.com/bhuvzzs24-spec/Eraseproof-x",
            styles["CoverSmall"],
        ),
        PageBreak(),
        Paragraph("Contents", styles["Chapter"]),
    ]
    toc = TableOfContents()
    toc.levelStyles = [styles["TOC"]]
    story += [toc, PageBreak()]
    markdown = source.read_text()
    start = re.search(r"^## 1\. ", markdown, flags=re.M)
    if not start:
        raise ValueError("chapter structure missing")
    tokens = MarkdownIt("commonmark").enable("table").parse(markdown[start.start() :])
    figures = json.loads((FOLDER / "diagrams/manifest.json").read_text())["figures"]
    index = 0
    figure_index = 0
    first_chapter = True
    lists = []
    item_first = []

    def image_flow(path, caption, diagram=False):
        if not path.is_file():
            raise FileNotFoundError(path)
        width, height = ImageReader(str(path)).getSize()
        horizontal_page = width / height > 3.0
        max_w = (wide[0] - 96) if horizontal_page else (A4[0] - 96)
        max_h = (wide[1] - 140) if horizontal_page else (A4[1] - 190)
        scale = min(max_w / width, max_h / height)
        elements = []
        if horizontal_page:
            heading = (
                story.pop()
                if story
                and isinstance(story[-1], Paragraph)
                and story[-1].style.name in ("Heading2", "Heading3", "Section")
                else None
            )
            elements += [NextPageTemplate("landscape"), PageBreak()]
            if heading is not None:
                elements.append(heading)
        heading = None
        if (
            not horizontal_page
            and story
            and isinstance(story[-1], Paragraph)
            and story[-1].style.name in ("Section", "Minor")
        ):
            heading = story.pop()
        elements += [
            KeepTogether(
                ([heading] if heading is not None else [])
                + [
                    Image(str(path), width=width * scale, height=height * scale),
                    Spacer(1, 8),
                    Paragraph(escape(clean(caption)), styles["Caption"]),
                ]
            )
        ]
        if horizontal_page:
            elements += [NextPageTemplate("portrait"), PageBreak()]
        return elements

    while index < len(tokens):
        token = tokens[index]
        if token.type == "heading_open":
            level = int(token.tag[1])
            content = inline(tokens[index + 1].children)
            if level == 2:
                if not first_chapter:
                    story.append(PageBreak())
                first_chapter = False
                style = styles["Chapter"]
            else:
                style = styles["Section"] if level == 3 else styles["Minor"]
            story.append(Paragraph(content, style))
            index += 3
            continue
        if token.type == "paragraph_open":
            child = tokens[index + 1]
            images = [t for t in child.children or [] if t.type == "image"]
            if images:
                for item in images:
                    src = (source.parent / (item.attrGet("src") or "")).resolve()
                    if not src.is_relative_to(ROOT):
                        raise ValueError("external/local-outside-repository images forbidden")
                    story += image_flow(src, item.content)
            else:
                bullet = None
                style = styles["ReportBody"]
                if lists:
                    style = styles["ListBody"]
                    if item_first and item_first[-1]:
                        bullet = (str(lists[-1][1]) + ".") if lists[-1][0] == "ordered" else "-"
                        item_first[-1] = False
                story.append(Paragraph(inline(child.children), style, bulletText=bullet))
            index += 3
            continue
        if token.type in ("bullet_list_open", "ordered_list_open"):
            lists.append(["ordered" if token.type.startswith("ordered") else "bullet", 0])
            index += 1
            continue
        if token.type in ("bullet_list_close", "ordered_list_close"):
            lists.pop()
            index += 1
            continue
        if token.type == "list_item_open":
            if lists:
                lists[-1][1] += 1
            item_first.append(True)
            index += 1
            continue
        if token.type == "list_item_close":
            item_first.pop()
            index += 1
            continue
        if token.type == "table_open":
            rows = []
            row = []
            cursor = index + 1
            while cursor < len(tokens) and tokens[cursor].type != "table_close":
                if tokens[cursor].type == "tr_open":
                    row = []
                if tokens[cursor].type == "inline":
                    row.append(Paragraph(inline(tokens[cursor].children), styles["Cell"]))
                if tokens[cursor].type == "tr_close":
                    rows.append(row)
                cursor += 1
            if rows:
                count = len(rows[0])
                width = A4[0] - 96
                if count == 2:
                    widths = [width * 0.30, width * 0.70]
                elif count == 3:
                    widths = [width * 0.24, width * 0.43, width * 0.33]
                else:
                    widths = [width / count] * count
                table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT", splitByRow=1)
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), PALE),
                            ("LINEBELOW", (0, 0), (-1, 0), 0.7, LINE),
                            ("LINEBELOW", (0, 1), (-1, -1), 0.25, LINE),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                            ("TOPPADDING", (0, 0), (-1, -1), 6),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                            (
                                "ROWBACKGROUNDS",
                                (0, 1),
                                (-1, -1),
                                [colors.white, colors.HexColor("#fafbfd")],
                            ),
                        ]
                    )
                )
                story += [Spacer(1, 5), table, Spacer(1, 11)]
            index = cursor + 1
            continue
        if token.type == "fence":
            if token.info.strip() == "mermaid":
                figure = figures[figure_index]
                if figure["source_sha256"] != sha256(token.content.encode()).hexdigest():
                    raise ValueError("diagram source hash mismatch; rerender diagrams")
                story += image_flow(
                    FOLDER / "diagrams" / figure["png"],
                    f"Figure {figure_index + 1}. Generated from the report's diagram-as-code. Static architecture/protocol metadata, not live traffic.",
                    True,
                )
                figure_index += 1
            else:
                lines = []
                for line in clean(token.content).splitlines():
                    lines.extend(
                        textwrap.wrap(
                            line,
                            width=100,
                            replace_whitespace=False,
                            drop_whitespace=False,
                            break_long_words=True,
                            break_on_hyphens=False,
                        )
                        or [""]
                    )
                story.append(Preformatted("\n".join(lines), styles["ReportCode"]))
            index += 1
            continue
        if token.type == "hr":
            story.append(Spacer(1, 12))
        index += 1
    document.multiBuild(story)
    print("Built PDF:", output, "with", figure_index, "rendered source diagrams")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", type=Path, default=FOLDER / "EraseProof-X-Complete-Technical-Report.md"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output/pdf/EraseProof-X-Complete-Technical-Report.pdf",
    )
    parser.add_argument("--runtime-sha", default="04a822001b10a9772cd9c5d0aeb607c372a497a1")
    args = parser.parse_args()
    build(args.source, args.output, args.runtime_sha)
