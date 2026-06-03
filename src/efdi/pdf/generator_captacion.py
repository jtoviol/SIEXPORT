"""Generador PDF para Gestión Captación Afiliados.

Mismo lenguaje visual que SOPORTE DEMANDA INDUCIDA y SOPORTE ENCUESTAS FINDRISC:
- Header limpio: logo Mutualser a la izquierda + título centrado en azul.
- Sección DATOS DEL AFILIADO.
- Sección CAPTACIÓN (estado, funcionario, fuente, fecha, IPS).
- Sección PROGRAMAS con grid de 19 banderas. Solo las que la BD trae como "SI"
  se marcan en verde (fondo + borde) — mismo estilo de marcado que DI.

Política: el contenido es literal de la BD. No clasifica, no calcula, no infiere.
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

from efdi.domain.models import CAPTACION_PROGRAMAS, AfiliadoConCaptacion, RegistroCaptacion

# ─── Paleta (consistente con DI y FINDRISC) ──────────────────────────────────
COLOR_SECTION     = colors.HexColor("#234674")
COLOR_QUESTION_BG = colors.HexColor("#E9EEF5")
COLOR_BORDER      = colors.HexColor("#B0BEC9")
COLOR_TEXT        = colors.HexColor("#1A1A1A")
COLOR_LABEL       = colors.HexColor("#3D4654")
COLOR_MARK_BG     = colors.HexColor("#DCFCE7")
COLOR_MARK_BORDER = colors.HexColor("#16A34A")
COLOR_MARK_TEXT   = colors.HexColor("#15803D")

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
STYLE_FLAG = ParagraphStyle(
    "Flag", parent=_styles["Normal"],
    fontName="Helvetica", fontSize=8, textColor=COLOR_TEXT, leading=10,
    alignment=TA_CENTER,
)
STYLE_FOOTER = ParagraphStyle(
    "Footer", parent=_styles["Normal"],
    fontName="Helvetica-Oblique", fontSize=6, textColor=colors.grey,
    alignment=TA_CENTER,
)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _raw(v: str | None) -> str:
    if v is None:
        return "—"
    s = str(v).strip()
    return s or "—"


# ─── Bloques visuales ────────────────────────────────────────────────────────

def _banner(width: float) -> Table:
    """Header: logo Mutualser + título centrado. Sin franja de color."""
    logo = Image(str(LOGO_MUTUALSER), width=2.4*cm, height=1.4*cm, kind="proportional") if LOGO_MUTUALSER.exists() else ""
    titulo = Paragraph("SOPORTE GESTIÓN CAPTACIÓN AFILIADOS", STYLE_TITLE)
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
    """Recibe una lista de filas, cada fila es lista de (label, value).
    Crea una tabla con celdas label/value apiladas."""

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


def _datos_afiliado(reg: RegistroCaptacion, width: float) -> Table:
    doc_full = f"{_raw(reg.tipo_identificacion_desc)}: {_raw(reg.num_documento)}"
    return _label_value_grid([
        [("Nombre del afiliado", _raw(reg.nombre_completo)),
         ("Sexo", _raw(reg.genero))],
        [("Edad", _raw(reg.edad)),
         ("Documento", doc_full),
         ("Fecha de nacimiento", _raw(reg.fec_nacimiento))],
        [("Regional", _raw(reg.regional)),
         ("Departamento", _raw(reg.departamento)),
         ("Municipio", _raw(reg.municipio))],
        [("Dirección actual", _raw(reg.direccion))],
        [("Teléfono celular", _raw(reg.telefono_celular)),
         ("Teléfono fijo", _raw(reg.telefono_fijo)),
         ("Teléfono familiar", _raw(reg.telefono_familiar))],
        [("Correo electrónico", _raw(reg.correo))],
    ], width)


def _datos_captacion(reg: RegistroCaptacion, width: float) -> Table:
    return _label_value_grid([
        [("Fecha de captación", _raw(reg.fecha_captacion_str)),
         ("Estado", _raw(reg.estado))],
        [("Funcionario", _raw(reg.funcionario)),
         ("Fuente de captación", _raw(reg.fuente_captacion))],
        [("IPS prestador de servicios", _raw(reg.prestador_servicios))],
    ], width)


def _programas_grid(reg: RegistroCaptacion, width: float) -> Table:
    """Grid de 19 banderas. La que la BD trae 'SI' lleva fondo verde + borde verde."""
    cells = []
    marcadas_idx: list[int] = []
    for i, (attr, label) in enumerate(CAPTACION_PROGRAMAS):
        marcada = reg.flag_marcado(attr)
        if marcada:
            html = f'<font color="#15803D"><b>{label}</b></font>'
            marcadas_idx.append(i)
        else:
            html = label
        cells.append(Paragraph(html, STYLE_FLAG))

    # Repartir en una cuadrícula 4 columnas × 5 filas (19 items + 1 espacio)
    n_cols = 4
    n_rows = (len(cells) + n_cols - 1) // n_cols
    grid: list[list[object]] = []
    pos_marcadas: list[tuple[int, int]] = []
    for r in range(n_rows):
        fila: list[object] = []
        for c in range(n_cols):
            idx = r * n_cols + c
            if idx < len(cells):
                fila.append(cells[idx])
                if idx in marcadas_idx:
                    pos_marcadas.append((r, c))
            else:
                fila.append("")
        grid.append(fila)

    col_w = width / n_cols
    t = Table(grid, colWidths=[col_w] * n_cols)
    style_cmds = [
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
        ("BOX",          (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID",    (0, 0), (-1, -1), 0.25, COLOR_BORDER),
    ]
    for (r, c) in pos_marcadas:
        style_cmds.append(("BACKGROUND", (c, r), (c, r), COLOR_MARK_BG))
        style_cmds.append(("BOX",        (c, r), (c, r), 1.2, COLOR_MARK_BORDER))
    t.setStyle(TableStyle(style_cmds))
    return t


# ─── Composición del documento ────────────────────────────────────────────────

def _construir_pagina_captacion(afiliado: AfiliadoConCaptacion) -> list:
    reg = afiliado.registros[0]
    width = letter[0] - 20 * mm

    elems: list = []
    elems.append(_banner(width))
    elems.append(Spacer(1, 4))

    elems.append(_section_header("DATOS DEL AFILIADO", width))
    elems.append(_datos_afiliado(reg, width))
    elems.append(Spacer(1, 4))

    elems.append(_section_header("CAPTACIÓN", width))
    elems.append(_datos_captacion(reg, width))
    elems.append(Spacer(1, 4))

    elems.append(_section_header("PROGRAMAS ASOCIADOS", width))
    elems.append(Spacer(1, 2))
    elems.append(_programas_grid(reg, width))

    # Si hay más de un registro para la misma fecha, listamos extras de forma compacta
    if len(afiliado.registros) > 1:
        elems.append(Spacer(1, 6))
        extras = []
        for i, r in enumerate(afiliado.registros[1:], start=2):
            extras.append(Paragraph(
                f"<b>#{i}</b> · Estado: {_raw(r.estado)} · Funcionario: {_raw(r.funcionario)} · Fuente: {_raw(r.fuente_captacion)}",
                STYLE_VALUE,
            ))
        info = Table([[p] for p in extras], colWidths=[width])
        info.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, -1), COLOR_QUESTION_BG),
            ("BOX",         (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",(0, 0), (-1, -1), 6),
            ("TOPPADDING",  (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ]))
        elems.append(Paragraph(
            f"<font color='#234674'><b>{len(afiliado.registros)} registros de captación en esta misma fecha</b></font>",
            STYLE_VALUE,
        ))
        elems.append(Spacer(1, 2))
        elems.append(info)

    return elems


def generar_pdf_captacion(afiliado: AfiliadoConCaptacion, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=10*mm, rightMargin=10*mm,
        topMargin=8*mm, bottomMargin=8*mm,
        title=f"Gestión Captación — {afiliado.pdf_key}",
        author="SIEDFASER",
    )
    elems = _construir_pagina_captacion(afiliado)
    elems.append(Spacer(1, 6))
    elems.append(Paragraph(
        "Documento generado automáticamente por SIEDFASER — Gestión Captación Afiliados",
        STYLE_FOOTER,
    ))
    doc.build(elems)
    return output_path
