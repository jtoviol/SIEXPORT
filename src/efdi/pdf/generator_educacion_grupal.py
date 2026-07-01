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
    from datetime import date as _date

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=15,
        rightMargin=15,
        topMargin=15,
        bottomMargin=15,
    )
    story: list = []

    # ── Derivados del lote de sesiones (periodo, conteos) ─────────────────
    fechas = [r.fec_educacion_grupal for r in afiliado.registros if r.fec_educacion_grupal]
    periodo_txt = ""
    if fechas:
        fmin, fmax = min(fechas), max(fechas)
        periodo_txt = f"Período: {fmin} al {fmax}" if fmin != fmax else f"Sesión del {fmin}"

    mod_counter: dict[str, int] = {}
    for r in afiliado.registros:
        m = (r.des_modalidad or "OTROS").upper()
        mod_counter[m] = mod_counter.get(m, 0) + 1
    mod_breakdown = " · ".join(f"{m.capitalize()}: {n}" for m, n in sorted(mod_counter.items()))

    eje_counter: dict[str, int] = {}
    for r in afiliado.registros:
        e = (r.des_eje_tematico or "—").upper()
        eje_counter[e] = eje_counter.get(e, 0) + 1

    regimen = afiliado.registros[0].regimen if afiliado.registros else None
    regimen_final = regimen or regimen_override or "—"

    # ── Header: logo + título + fecha de emisión ──────────────────────────
    emitido_txt = f"Generado: {_date.today().strftime('%d/%m/%Y')}"
    logo_exists = LOGO_MUTUALSER.exists()
    img = Image(str(LOGO_MUTUALSER), width=1.8*cm, height=1.2*cm) if logo_exists else Paragraph("", STYLE_VALUE)
    header_table = Table(
        [[img, Paragraph("SOPORTE EDUCACIÓN GRUPAL", STYLE_TITLE), Paragraph(emitido_txt, STYLE_LABEL)]],
        colWidths=[2.2*cm, 370, 100],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (0, 0), 0),
            ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ]),
    )
    story.append(header_table)
    if periodo_txt:
        story.append(Spacer(1, 2))
        story.append(Paragraph(periodo_txt, STYLE_LABEL))
    story.append(Spacer(1, 6))

    # ── Datos del afiliado ───────────────────────────────────────────────
    story.append(_section_header("DATOS DEL AFILIADO"))
    story.append(Spacer(1, 2))
    total_breakdown = f"{afiliado.total_sesiones}"
    if mod_breakdown:
        total_breakdown += f" ({mod_breakdown})"
    datos = [
        _label_value_row("Documento", f"{afiliado.tipo_documento} {afiliado.num_documento}"),
        _label_value_row("Nombre", afiliado.nombre_completo),
        _label_value_row("Régimen", regimen_final),
        _label_value_row("Total sesiones", total_breakdown),
    ]
    for row in datos:
        t = Table([row], colWidths=[100, 380])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        story.append(t)
    story.append(Spacer(1, 8))

    # ── Ficha por sesión ──────────────────────────────────────────────────
    total = afiliado.total_sesiones
    for i, reg in enumerate(afiliado.registros, 1):
        story.append(_section_header(f"SESIÓN {i} DE {total}"))
        story.append(Spacer(1, 2))

        depto_muni = " / ".join([p for p in [reg.departamento, reg.municipio] if p]) or "—"
        ficha_rows = [
            [
                Paragraph("<b>Fecha sesión:</b>", STYLE_LABEL),
                Paragraph(reg.fec_educacion_grupal or "—", STYLE_VALUE),
                Paragraph("<b>Registrado:</b>", STYLE_LABEL),
                Paragraph(reg.fec_registro_educacion or "—", STYLE_VALUE),
            ],
            [
                Paragraph("<b>Curso de vida:</b>", STYLE_LABEL),
                Paragraph(reg.des_curso_vida_asociado or "—", STYLE_VALUE),
                "", "",
            ],
            [
                Paragraph("<b>Eje temático:</b>", STYLE_LABEL),
                Paragraph(reg.des_eje_tematico or "—", STYLE_VALUE),
                Paragraph("<b>Modalidad:</b>", STYLE_LABEL),
                Paragraph(reg.des_modalidad or "—", STYLE_VALUE),
            ],
            [
                Paragraph("<b>Facilitador:</b>", STYLE_LABEL),
                Paragraph(reg.facilitador or "—", STYLE_VALUE),
                "", "",
            ],
            [
                Paragraph("<b>Ubicación:</b>", STYLE_LABEL),
                Paragraph(reg.txt_ubicacion_fisica or "—", STYLE_VALUE),
                "", "",
            ],
            [
                Paragraph("<b>Depto / Mpio:</b>", STYLE_LABEL),
                Paragraph(depto_muni, STYLE_VALUE),
                "", "",
            ],
        ]
        ficha_tbl = Table(
            ficha_rows,
            colWidths=[90, 200, 70, 120],
            style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.4, COLOR_BORDER),
                ("LINEBELOW", (0, 0), (-1, -2), 0.2, COLOR_ALT_ROW),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("SPAN", (1, 1), (3, 1)),
                ("SPAN", (1, 3), (3, 3)),
                ("SPAN", (1, 4), (3, 4)),
                ("SPAN", (1, 5), (3, 5)),
            ]),
        )
        story.append(ficha_tbl)
        story.append(Spacer(1, 6))

    # ── Resumen ───────────────────────────────────────────────────────────
    story.append(Spacer(1, 4))
    story.append(_section_header("RESUMEN"))
    story.append(Spacer(1, 2))

    mod_txt = " · ".join(f"{m.capitalize()} {n}" for m, n in sorted(mod_counter.items())) or "—"
    eje_txt = " · ".join(f"{e} {n}" for e, n in sorted(eje_counter.items(), key=lambda x: -x[1])) or "—"
    periodo_resumen = periodo_txt.replace("Período: ", "").replace("Sesión del ", "") if periodo_txt else "—"

    resumen_rows = [
        _label_value_row("Por modalidad", mod_txt),
        _label_value_row("Por eje temático", eje_txt),
        _label_value_row("Período cubierto", periodo_resumen),
    ]
    for row in resumen_rows:
        t = Table([row], colWidths=[110, 370])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        story.append(t)
    story.append(Spacer(1, 10))

    story.append(Paragraph(
        "Sistema Inteligente de Exportación de Datos para Facturación — SIEDFASER",
        STYLE_FOOTER,
    ))

    doc.build(story)
