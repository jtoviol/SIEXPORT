"""Generador PDF Educación Grupal — 1 PDF por afiliado con sus sesiones."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from efdi.domain.models import AfiliadoConEducacionGrupal, RegistroEducacionGrupal

COLOR_SECTION      = colors.HexColor("#234674")
COLOR_BORDER       = colors.HexColor("#B0BEC9")
COLOR_TEXT         = colors.HexColor("#1A1A1A")
COLOR_LABEL        = colors.HexColor("#3D4654")
COLOR_HEADER_BG    = colors.HexColor("#234674")
COLOR_ALT_ROW      = colors.HexColor("#F5F7FA")

LOGO_MUTUALSER = Path(__file__).parent.parent / "templates" / "logo.png"

_styles = getSampleStyleSheet()

STYLE_TITLE = ParagraphStyle(
    "Title", parent=_styles["Heading1"],
    fontName="Helvetica-Bold", fontSize=14, textColor=COLOR_SECTION,
    alignment=TA_CENTER, leading=16,
)
STYLE_SECTION = ParagraphStyle(
    "Section", parent=_styles["Heading2"],
    fontName="Helvetica-Bold", fontSize=8, textColor=colors.white,
    alignment=TA_LEFT, leading=10, leftIndent=4,
)
STYLE_LABEL = ParagraphStyle(
    "Label", parent=_styles["Normal"],
    fontName="Helvetica-Bold", fontSize=7, textColor=COLOR_LABEL, leading=9,
)
STYLE_VALUE = ParagraphStyle(
    "Value", parent=_styles["Normal"],
    fontName="Helvetica", fontSize=8, textColor=COLOR_TEXT, leading=10,
)
STYLE_CELL = ParagraphStyle(
    "Cell", parent=_styles["Normal"],
    fontName="Helvetica", fontSize=7, textColor=COLOR_TEXT, leading=9, alignment=TA_LEFT,
)
STYLE_FOOTER = ParagraphStyle(
    "Footer", parent=_styles["Normal"],
    fontName="Helvetica-Oblique", fontSize=6, textColor=colors.grey,
    alignment=TA_CENTER,
)


def _section_header(text: str):
    return Table(
        [[Paragraph(text, STYLE_SECTION)]],
        colWidths=[480],
        rowHeights=14,
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_HEADER_BG),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]),
    )


def _label_value_row(label: str, value: str):
    return [
        Paragraph(f"<b>{label}:</b>", STYLE_LABEL),
        Paragraph(value or "—", STYLE_VALUE),
    ]


def generar_pdf_educacion_grupal(
    afiliado: AfiliadoConEducacionGrupal,
    output_path: Path,
    regimen_override: str | None = None,
) -> None:
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=15,
        rightMargin=15,
        topMargin=15,
        bottomMargin=15,
    )
    story: list = []

    # Logo + título
    logo_exists = LOGO_MUTUALSER.exists()
    if logo_exists:
        img = Image(str(LOGO_MUTUALSER), width=1.8*cm, height=1.2*cm)
    else:
        img = Paragraph("", STYLE_VALUE)
    header_table = Table(
        [[img, Paragraph("SOPORTE EDUCACIÓN GRUPAL", STYLE_TITLE)]],
        colWidths=[2.2*cm, 470],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (0, 0), 0),
        ]),
    )
    story.append(header_table)
    story.append(Spacer(1, 4))

    # Datos del afiliado
    story.append(_section_header("DATOS DEL AFILIADO"))
    story.append(Spacer(1, 2))
    datos = [
        _label_value_row("Documento", f"{afiliado.tipo_documento} {afiliado.num_documento}"),
        _label_value_row("Nombre", afiliado.nombre_completo),
        _label_value_row("Total sesiones", str(afiliado.total_sesiones)),
    ]
    for row in datos:
        t = Table([row], colWidths=[100, 380])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        story.append(t)
    story.append(Spacer(1, 6))

    # Tabla de sesiones educativas
    story.append(_section_header("SESIONES EDUCATIVAS ASISTIDAS"))
    story.append(Spacer(1, 2))

    header_row = [
        Paragraph("<b>#</b>", STYLE_CELL),
        Paragraph("<b>Fecha</b>", STYLE_CELL),
        Paragraph("<b>Curso de Vida</b>", STYLE_CELL),
        Paragraph("<b>Eje Temático</b>", STYLE_CELL),
        Paragraph("<b>Modalidad</b>", STYLE_CELL),
        Paragraph("<b>Facilitador</b>", STYLE_CELL),
        Paragraph("<b>Ubicación</b>", STYLE_CELL),
    ]
    data_rows = [header_row]
    for i, reg in enumerate(afiliado.registros, 1):
        data_rows.append([
            Paragraph(str(i), STYLE_CELL),
            Paragraph(reg.fec_educacion_grupal or "—", STYLE_CELL),
            Paragraph(reg.des_curso_vida_asociado or "—", STYLE_CELL),
            Paragraph(reg.des_eje_tematico or "—", STYLE_CELL),
            Paragraph(reg.des_modalidad or "—", STYLE_CELL),
            Paragraph(reg.facilitador or "—", STYLE_CELL),
            Paragraph(f"{reg.departamento or ''} / {reg.municipio or ''}".strip(" / ") or "—", STYLE_CELL),
        ])

    col_widths = [20, 55, 90, 90, 60, 90, 95]
    table = Table(data_rows, colWidths=col_widths, repeatRows=1)
    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, COLOR_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]
    for idx in range(1, len(data_rows)):
        if idx % 2 == 0:
            table_style.append(("BACKGROUND", (0, idx), (-1, idx), COLOR_ALT_ROW))
    table.setStyle(TableStyle(table_style))
    story.append(table)

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Total de sesiones educativas asistidas: {afiliado.total_sesiones}",
        STYLE_VALUE,
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Sistema Inteligente de Exportación de Datos para Facturación — SIEDFASER",
        STYLE_FOOTER,
    ))

    doc.build(story)
