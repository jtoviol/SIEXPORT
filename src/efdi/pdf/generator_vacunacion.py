"""Generador PDF SOPORTE VACUNACIÓN — formato tipo carné.

Diseño:
- Banner superior con logo SIEDFASER + título "SOPORTE VACUNACIÓN"
- Datos del afiliado (nombre, doc, sexo, edad, fecha nac, dirección, teléfono,
  correo, depto/muni, régimen)
- Tabla "Datos de Vacunación" con 1 fila por vacuna aplicada

El régimen viene del propio Excel (columna REGIMEN) — no hay override como en
los otros módulos porque no hay cruce contra AVS_REGISTROS_AP.
"""
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

from efdi.domain.models import AfiliadoConVacunas, RegistroVacuna

# ─── Paleta (consistente con FINDRISC/DI) ────────────────────────────────────
COLOR_SECTION      = colors.HexColor("#234674")   # azul institucional secciones
COLOR_ROW_ALT      = colors.HexColor("#F5F7FA")
COLOR_BORDER       = colors.HexColor("#B0BEC9")
COLOR_TEXT         = colors.HexColor("#1A1A1A")
COLOR_LABEL        = colors.HexColor("#3D4654")
COLOR_HEADER_TABLE = colors.HexColor("#E9EEF5")

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
STYLE_TABLE_HEADER = ParagraphStyle(
    "TableHeader", parent=_styles["Normal"],
    fontName="Helvetica-Bold", fontSize=7, textColor=COLOR_SECTION,
    alignment=TA_CENTER, leading=9,
)
STYLE_TABLE_CELL = ParagraphStyle(
    "TableCell", parent=_styles["Normal"],
    fontName="Helvetica", fontSize=7, textColor=COLOR_TEXT, leading=9,
)
STYLE_FOOTER = ParagraphStyle(
    "Footer", parent=_styles["Normal"],
    fontName="Helvetica-Oblique", fontSize=6, textColor=colors.grey,
    alignment=TA_CENTER,
)


# ─── helpers ────────────────────────────────────────────────────────────────

def _sn(v: object, default: str = "—") -> str:
    s = str(v).strip() if v is not None else ""
    return s or default


def _fmt_fecha(f) -> str:
    if not f:
        return "—"
    try:
        return f.strftime("%d/%m/%Y")
    except AttributeError:
        return str(f)


# ─── Bloques visuales ───────────────────────────────────────────────────────

def _banner(width: float) -> Table:
    """Header: logo SIEDFASER a la izquierda + título centrado.
    Misma estructura que FINDRISC para mantener consistencia visual."""
    logo_m = Image(str(LOGO_MUTUALSER), width=2.4*cm, height=1.4*cm, kind="proportional") if LOGO_MUTUALSER.exists() else ""
    titulo = Paragraph("SOPORTE VACUNACIÓN", STYLE_TITLE)

    t = Table(
        [[logo_m, titulo, ""]],
        colWidths=[2.8*cm, width - 5.6*cm, 2.8*cm],
    )
    t.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",        (0, 0), (0, 0),   "LEFT"),
        ("ALIGN",        (1, 0), (1, 0),   "CENTER"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
        ("LINEBELOW",    (0, 0), (-1, -1), 1, COLOR_SECTION),
    ]))
    return t


def _section_header(text: str, width: float) -> Table:
    t = Table([[Paragraph(text, STYLE_SECTION)]], colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), COLOR_SECTION),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",  (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
    ]))
    return t


def _datos_afiliado(afi: AfiliadoConVacunas, width: float) -> Table:
    """Bloque de datos demográficos del afiliado.
    Mismo estilo de cells que FINDRISC."""
    def cell(label: str, value: str) -> Table:
        inner = Table(
            [[Paragraph(label, STYLE_LABEL)], [Paragraph(value, STYLE_VALUE)]],
            colWidths=[None],
        )
        inner.setStyle(TableStyle([
            ("LEFTPADDING",  (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING",   (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 1),
        ]))
        return inner

    doc_full = f"{_sn(afi.tipo_identificacion_desc, afi.tipo_documento)}: {_sn(afi.num_documento)}"
    regimen_str = _sn(afi.regimen)
    municipio_full = ", ".join(filter(None, [afi.municipio, afi.departamento])) or "—"

    row1 = [cell("Nombre del afiliado", _sn(afi.nombre_completo)),
            cell("Sexo", _sn(afi.sexo))]
    row2 = [cell("Edad actual", f"{afi.edad} años"),
            cell("Fecha de nacimiento", _fmt_fecha(afi.fecha_nacimiento)),
            cell("Documento", doc_full)]
    row3 = [cell("Teléfono 1", _sn(afi.telefono_1)),
            cell("Teléfono 2", _sn(afi.telefono_2)),
            cell("Régimen", regimen_str)]
    row4 = [cell("Correo electrónico", _sn(afi.correo)),
            cell("Municipio / Departamento", municipio_full)]
    row5 = [cell("Dirección", _sn(afi.direccion))]

    tablas = []
    for row, widths in [
        (row1, [width * 0.62, width * 0.38]),
        (row2, [width * 0.20, width * 0.42, width * 0.38]),
        (row3, [width * 0.34, width * 0.34, width * 0.32]),
        (row4, [width * 0.50, width * 0.50]),
        (row5, [width]),
    ]:
        t = Table([row], colWidths=widths)
        t.setStyle(TableStyle([
            ("BOX",         (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("INNERGRID",   (0, 0), (-1, -1), 0.3, COLOR_BORDER),
            ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ]))
        tablas.append(t)

    wrap = Table([[t] for t in tablas], colWidths=[width])
    wrap.setStyle(TableStyle([
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 1),
    ]))
    return wrap


def _tabla_vacunas(vacunas: list[RegistroVacuna], width: float) -> Table:
    """Tabla con todas las vacunas del afiliado.
    Columnas: Vacuna | Fecha | Modo Ingreso | Municipio | Vacunador"""
    header = [
        Paragraph("Vacuna", STYLE_TABLE_HEADER),
        Paragraph("Fecha de aplicación", STYLE_TABLE_HEADER),
        Paragraph("Modo de ingreso", STYLE_TABLE_HEADER),
        Paragraph("Municipio", STYLE_TABLE_HEADER),
        Paragraph("Vacunador", STYLE_TABLE_HEADER),
    ]
    rows: list[list[Paragraph]] = [header]
    # Orden estable: por fecha ascendente, luego por nombre de programa
    vacunas_ord = sorted(vacunas, key=lambda v: (v.fecha_aplicacion, v.programa or ""))
    for v in vacunas_ord:
        rows.append([
            Paragraph(_sn(v.programa), STYLE_TABLE_CELL),
            Paragraph(_fmt_fecha(v.fecha_aplicacion), STYLE_TABLE_CELL),
            Paragraph(_sn(v.modo_ingreso), STYLE_TABLE_CELL),
            Paragraph(_sn(v.municipio), STYLE_TABLE_CELL),
            Paragraph(_sn(v.encuestador), STYLE_TABLE_CELL),
        ])

    col_widths = [
        width * 0.32,   # Vacuna (más ancha — nombres largos)
        width * 0.14,   # Fecha
        width * 0.14,   # Modo
        width * 0.18,   # Municipio
        width * 0.22,   # Vacunador
    ]
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    estilo = [
        ("BACKGROUND",   (0, 0), (-1, 0), COLOR_HEADER_TABLE),
        ("BOX",          (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID",    (0, 0), (-1, -1), 0.3, COLOR_BORDER),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",        (0, 0), (-1, 0),   "CENTER"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
    ]
    # Alternar filas de datos
    for i in range(1, len(rows)):
        if i % 2 == 0:
            estilo.append(("BACKGROUND", (0, i), (-1, i), COLOR_ROW_ALT))
    t.setStyle(TableStyle(estilo))
    return t


# ─── Composición del documento ──────────────────────────────────────────────

def _construir_pagina(afiliado: AfiliadoConVacunas) -> list:
    width = letter[0] - 20 * mm  # ancho usable

    elems: list = []
    elems.append(_banner(width))
    elems.append(Spacer(1, 4))

    elems.append(_section_header("DATOS DEL AFILIADO", width))
    elems.append(_datos_afiliado(afiliado, width))
    elems.append(Spacer(1, 6))

    elems.append(_section_header(
        f"DATOS DE VACUNACIÓN  ({afiliado.total_vacunas} aplicaciones)", width,
    ))
    elems.append(_tabla_vacunas(afiliado.vacunas, width))

    elems.append(Spacer(1, 8))
    elems.append(Paragraph(
        "Documento generado por SIEDFASER — Sistema Inteligente de Exportación "
        "de Datos para Facturación de Seragil.",
        STYLE_FOOTER,
    ))
    return elems


def generar_pdf_vacunacion(
    afiliado: AfiliadoConVacunas,
    output_path: Path,
) -> Path:
    """Genera UN PDF carné con todas las vacunas del afiliado."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=10*mm, rightMargin=10*mm,
        topMargin=10*mm,  bottomMargin=10*mm,
        title=f"Soporte Vacunación · {afiliado.doc_key}",
        author="SIEDFASER",
    )
    doc.build(_construir_pagina(afiliado))
    return output_path
