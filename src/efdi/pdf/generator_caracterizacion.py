"""Generador PDF para Caracterización Familiar (base sibacom).

Mismo lenguaje visual que los demás módulos:
- Header limpio: logo Mutualser a la izquierda + título centrado en azul.
- Secciones: ÁREA GEOGRÁFICA / UBICACIÓN DE LA FAMILIA / un bloque
  INTEGRANTE #N DE M por cada persona de la familia.

Política de fidelidad total: contenido literal de la BD, etiquetas con los
mismos nombres que los alias de la consulta.
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

from efdi.domain.models import FamiliaCaracterizada, RegistroCaracterizacion

# ─── Paleta (consistente con DI/FINDRISC/Captación/PlanFami) ─────────────────
COLOR_SECTION = colors.HexColor("#234674")
COLOR_BORDER  = colors.HexColor("#B0BEC9")
COLOR_TEXT    = colors.HexColor("#1A1A1A")
COLOR_LABEL   = colors.HexColor("#3D4654")

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
STYLE_FOOTER = ParagraphStyle(
    "Footer", parent=_styles["Normal"],
    fontName="Helvetica-Oblique", fontSize=6, textColor=colors.grey,
    alignment=TA_CENTER,
)


def _raw(v: str | None) -> str:
    if v is None:
        return "—"
    s = str(v).strip()
    return s or "—"


# ─── Bloques visuales ────────────────────────────────────────────────────────

def _banner(width: float) -> Table:
    logo = (Image(str(LOGO_MUTUALSER), width=2.4*cm, height=1.4*cm, kind="proportional")
            if LOGO_MUTUALSER.exists() else "")
    titulo = Paragraph("SOPORTE CARACTERIZACIÓN FAMILIAR", STYLE_TITLE)
    t = Table([[logo, titulo, ""]], colWidths=[2.8*cm, width - 5.6*cm, 2.8*cm])
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
        ("BACKGROUND",   (0, 0), (-1, -1), COLOR_SECTION),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
    ]))
    return t


def _label_value_grid(rows: list[list[tuple[str, str]]], width: float) -> Table:
    def cell(label: str, value: str) -> Table:
        inner = Table(
            [[Paragraph(label, STYLE_LABEL)], [Paragraph(value, STYLE_VALUE)]],
            colWidths=[None],
        )
        inner.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING",(0, 0), (-1, -1), 4),
            ("TOPPADDING",  (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 1),
        ]))
        return inner

    tablas = []
    for fila in rows:
        n = len(fila)
        col_w = [width / n] * n
        celdas = [cell(lab, val) for lab, val in fila]
        t = Table([celdas], colWidths=col_w)
        t.setStyle(TableStyle([
            ("BOX",         (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("INNERGRID",   (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("VALIGN",      (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",(0, 0), (-1, -1), 0),
            ("TOPPADDING",  (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
        ]))
        tablas.append(t)

    contenedor = Table([[t] for t in tablas], colWidths=[width])
    contenedor.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",(0, 0), (-1, -1), 0),
        ("TOPPADDING",  (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    return contenedor


def _area_geografica(reg: RegistroCaracterizacion, width: float) -> Table:
    return _label_value_grid([
        [("DEPARTAMENTO", _raw(reg.departamento)),
         ("MUNICIPIO", _raw(reg.municipio)),
         ("AREA", _raw(reg.area)),
         ("CORREGIMIENTO", _raw(reg.corregimiento))],
        [("BARRIO/VEREDA", _raw(reg.barrio_vereda)),
         ("MANZANA", _raw(reg.manzana)),
         ("VIVIENDA", _raw(reg.vivienda)),
         ("FAMILIA", _raw(reg.familia))],
        [("TIPO DE FAMILIA", _raw(reg.tipo_familia)),
         ("CIUF", _raw(reg.ciuf))],
    ], width)


def _ubicacion_familia(reg: RegistroCaracterizacion, width: float) -> Table:
    return _label_value_grid([
        [("FECHA REGISTRO", _raw(reg.fecha_registro)),
         ("COHORTE", _raw(reg.cohorte)),
         ("VISITA", _raw(reg.visita))],
        [("LATITUD", _raw(reg.latitud)),
         ("LONGITUD", _raw(reg.longitud))],
        [("SISBEN-GRUPO", _raw(reg.sisben_grupo)),
         ("SISBEN-SUBGRUPO", _raw(reg.sisben_subgrupo))],
        [("DIRECCION", _raw(reg.direccion))],
        [("TELEFONO_1", _raw(reg.telefono_1)),
         ("TELEFONO_2", _raw(reg.telefono_2)),
         ("CORREO ELECTRONICO", _raw(reg.correo))],
    ], width)


def _integrante(reg: RegistroCaracterizacion, width: float) -> Table:
    return _label_value_grid([
        [("NOMBRES Y APELLIDOS", _raw(reg.nombres_apellidos)),
         ("PARENTESCO FAMILIAR", _raw(reg.parentesco))],
        [("TIPO DOCUMENTO", _raw(reg.tipo_documento)),
         ("NUMERO DOCUMENTO", _raw(reg.num_documento)),
         ("SEXO", _raw(reg.sexo))],
        [("FECHA DE NACIMIENTO", _raw(reg.fecha_nacimiento)),
         ("EDAD", _raw(reg.edad)),
         ("UNIDADES", _raw(reg.unidades))],
        [("ESTUDIA ACTUALMENTE", _raw(reg.estudia)),
         ("AÑOS APROBADOS", _raw(reg.anos_aprobados))],
        [("NOMBRE OCUPACION", _raw(reg.nombre_ocupacion))],
        [("RÉGIMEN", _raw(reg.descripcion_regimen)),
         ("INSTITUCIÓN / EPS", _raw(reg.nombre_institucion))],
        [("ETNIA", _raw(reg.etnia)),
         ("G.A.E", _raw(reg.gae))],
        [("PROGRAMA", _raw(reg.programa)),
         ("DISCAPACIDAD", _raw(reg.discapacidad))],
    ], width)


# ─── Composición ─────────────────────────────────────────────────────────────

def _construir_pagina_caracterizacion(familia: FamiliaCaracterizada) -> list:
    reg = familia.registros[0]   # área geográfica y ubicación: compartidas por familia
    width = letter[0] - 20 * mm
    total = familia.total_integrantes

    elems: list = []
    elems.append(_banner(width))
    elems.append(Spacer(1, 4))

    elems.append(_section_header("ÁREA GEOGRÁFICA", width))
    elems.append(_area_geografica(reg, width))
    elems.append(Spacer(1, 4))

    elems.append(_section_header("UBICACIÓN DE LA FAMILIA", width))
    elems.append(_ubicacion_familia(reg, width))

    for i, r in enumerate(familia.registros, start=1):
        elems.append(Spacer(1, 6))
        elems.append(_section_header(f"INTEGRANTE #{i} DE {total}", width))
        elems.append(_integrante(r, width))

    return elems


def generar_pdf_caracterizacion(
    familia: FamiliaCaracterizada,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=10*mm, rightMargin=10*mm,
        topMargin=8*mm, bottomMargin=8*mm,
        title=f"Caracterización Familiar — {familia.pdf_key}",
        author="SIEDFASER",
    )
    elems = _construir_pagina_caracterizacion(familia)
    elems.append(Spacer(1, 6))
    elems.append(Paragraph(
        "Documento generado automáticamente por SIEDFASER — Caracterización Familiar",
        STYLE_FOOTER,
    ))
    doc.build(elems)
    return output_path
