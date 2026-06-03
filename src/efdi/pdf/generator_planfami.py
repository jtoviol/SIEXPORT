"""Generador PDF para Seguimiento Planificación Familiar.

Mismo lenguaje visual que los demás módulos:
- Header limpio: logo Mutualser a la izquierda + título centrado en azul.
- Secciones: DATOS DEL AFILIADO / UBICACIÓN Y PERÍODO / CAPTACIÓN /
  PLANIFICACIÓN / EVENTOS OBSTÉTRICOS / FACTORES CLÍNICOS (grid 13) /
  SEGUIMIENTO / OBSERVACIONES.

Política: contenido literal de la BD.
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

from efdi.domain.models import (
    PLANFAMI_FACTORES_CLINICOS,
    AfiliadoConPlanFamiliar,
    RegistroPlanFamiliar,
)

# ─── Paleta (consistente con DI/FINDRISC/Captación) ──────────────────────────
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
STYLE_FACTOR = ParagraphStyle(
    "Factor", parent=_styles["Normal"],
    fontName="Helvetica", fontSize=8, textColor=COLOR_TEXT, leading=10,
    alignment=TA_CENTER,
)
STYLE_OBS = ParagraphStyle(
    "Obs", parent=_styles["Normal"],
    fontName="Helvetica", fontSize=8, textColor=COLOR_TEXT, leading=11,
    alignment=TA_LEFT,
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
    titulo = Paragraph("SOPORTE SEGUIMIENTO PLANIFICACIÓN FAMILIAR", STYLE_TITLE)
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


def _datos_afiliado(reg: RegistroPlanFamiliar, width: float) -> Table:
    doc_full = f"{_raw(reg.tipo_identificacion_desc)}: {_raw(reg.num_documento)}"
    return _label_value_grid([
        [("Nombre del afiliado", _raw(reg.nombre_completo)),
         ("Documento", doc_full)],
        [("Fecha de nacimiento", _raw(reg.fecha_nacimiento)),
         ("Edad", f"{_raw(reg.edad)} años"),
         ("Régimen", _raw(reg.regimen))],
        [("Teléfono(s)", _raw(reg.telefono))],
    ], width)


def _ubicacion_periodo(reg: RegistroPlanFamiliar, width: float) -> Table:
    return _label_value_grid([
        [("Regional", _raw(reg.regional)),
         ("Departamento", _raw(reg.departamento)),
         ("Municipio", _raw(reg.municipio))],
        [("Año", _raw(reg.anio)),
         ("Trimestre", _raw(reg.trimestre)),
         ("Tipo de población", _raw(reg.tipo_poblacion))],
    ], width)


def _captacion(reg: RegistroPlanFamiliar, width: float) -> Table:
    return _label_value_grid([
        [("Fecha de gestión / seguimiento", _raw(reg.fecha_gestion_str)),
         ("Tipo de seguimiento", _raw(reg.tipo_seguimiento)),
         ("Estado", _raw(reg.estado))],
        [("Encuestador", _raw(reg.encuestador))],
    ], width)


def _planificacion(reg: RegistroPlanFamiliar, width: float) -> Table:
    return _label_value_grid([
        [("¿Planifica?", _raw(reg.flg_planifica)),
         ("Motivo no planifica", _raw(reg.motivo_no_planifica))],
        [("¿Desea utilizar método?", _raw(reg.flg_desea_utilizar_metodo)),
         ("Método anticonceptivo deseado", _raw(reg.metodo_anticonceptivo))],
        [("Método actual de planificación", _raw(reg.metodo_planificacion)),
         ("Fecha inicio PF", _raw(reg.fec_inicio_planfami))],
        [("Inicio preconcepcional", _raw(reg.flg_inicio_preconcepcional))],
    ], width)


def _eventos_obstetricos(reg: RegistroPlanFamiliar, width: float) -> Table:
    return _label_value_grid([
        [("Nº de eventos obstétricos", _raw(reg.nro_eventos_obstetricos)),
         ("Fuente del evento", _raw(reg.flg_fuente_evento_obstetrico))],
        [("Fecha evento planificación", _raw(reg.fec_evento_planificacion)),
         ("Código producto", _raw(reg.cod_producto_ev_planificacion))],
        [("Nombre producto", _raw(reg.nom_producto_ev_planificacion))],
        [("Fecha planificación 202", _raw(reg.fec_planificacion_202)),
         ("Variable 202", _raw(reg.var_planificacion_202))],
        [("Fecha planificación temporal", _raw(reg.fec_planificacion_temporal)),
         ("Fuente PF temporal", _raw(reg.cod_fuente_planificacion_temporal))],
        [("Método PF temporal", _raw(reg.des_metodo_planificacion_temporal))],
    ], width)


def _factores_clinicos_grid(reg: RegistroPlanFamiliar, width: float) -> Table:
    """Grid de 13 factores clínicos (FIC). El que la BD trae con valor → verde."""
    cells = []
    marcadas_idx: list[int] = []
    for i, (attr, label) in enumerate(PLANFAMI_FACTORES_CLINICOS):
        marcada = reg.factor_marcado(attr)
        if marcada:
            html = f'<font color="#15803D"><b>{label}</b></font>'
            marcadas_idx.append(i)
        else:
            html = label
        cells.append(Paragraph(html, STYLE_FACTOR))

    # Distribuir en 4 columnas × 4 filas (13 items + 3 espacios)
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


def _seguimiento(reg: RegistroPlanFamiliar, width: float) -> Table:
    return _label_value_grid([
        [("¿Contactada?", _raw(reg.flg_contactada)),
         ("¿Visita domiciliaria?", _raw(reg.flg_visita_domiciliaria)),
         ("¿Cierra seguimiento?", _raw(reg.flg_cierra_seguimiento))],
        [("Motivo de no contacto", _raw(reg.motivo_nocontacto))],
    ], width)


def _observaciones(reg: RegistroPlanFamiliar, width: float) -> Table:
    obs = (reg.observaciones or "").strip() or "—"
    p = Paragraph(obs, STYLE_OBS)
    t = Table([[p]], colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), COLOR_QUESTION_BG),
        ("BOX",         (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",(0, 0), (-1, -1), 8),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
    ]))
    return t


# ─── Composición ─────────────────────────────────────────────────────────────

def _construir_pagina_planfami(afiliado: AfiliadoConPlanFamiliar) -> list:
    reg = afiliado.registros[0]
    width = letter[0] - 20 * mm

    elems: list = []
    elems.append(_banner(width))
    elems.append(Spacer(1, 4))

    elems.append(_section_header("DATOS DEL AFILIADO", width))
    elems.append(_datos_afiliado(reg, width))
    elems.append(Spacer(1, 4))

    elems.append(_section_header("UBICACIÓN Y PERÍODO", width))
    elems.append(_ubicacion_periodo(reg, width))
    elems.append(Spacer(1, 4))

    elems.append(_section_header("CAPTACIÓN", width))
    elems.append(_captacion(reg, width))
    elems.append(Spacer(1, 4))

    elems.append(_section_header("PLANIFICACIÓN", width))
    elems.append(_planificacion(reg, width))
    elems.append(Spacer(1, 4))

    elems.append(_section_header("EVENTOS OBSTÉTRICOS", width))
    elems.append(_eventos_obstetricos(reg, width))
    elems.append(Spacer(1, 4))

    elems.append(_section_header("FACTORES CLÍNICOS", width))
    elems.append(Spacer(1, 2))
    elems.append(_factores_clinicos_grid(reg, width))
    elems.append(Spacer(1, 4))

    elems.append(_section_header("SEGUIMIENTO", width))
    elems.append(_seguimiento(reg, width))
    elems.append(Spacer(1, 4))

    elems.append(_section_header("OBSERVACIONES", width))
    elems.append(Spacer(1, 2))
    elems.append(_observaciones(reg, width))

    # Si hay más de un registro en la misma fecha de gestión, listarlos abajo
    if len(afiliado.registros) > 1:
        elems.append(Spacer(1, 6))
        elems.append(Paragraph(
            f"<font color='#234674'><b>{len(afiliado.registros)} seguimientos en esta misma fecha</b></font>",
            STYLE_VALUE,
        ))
        for i, r in enumerate(afiliado.registros[1:], start=2):
            extra = (
                f"<b>#{i}</b> · Estado: {_raw(r.estado)} · Tipo seg.: {_raw(r.tipo_seguimiento)} · "
                f"Encuestador: {_raw(r.encuestador)}"
            )
            elems.append(Paragraph(extra, STYLE_VALUE))

    return elems


def generar_pdf_planfami(afiliado: AfiliadoConPlanFamiliar, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=10*mm, rightMargin=10*mm,
        topMargin=8*mm, bottomMargin=8*mm,
        title=f"Planificación Familiar — {afiliado.pdf_key}",
        author="SIEDFASER",
    )
    elems = _construir_pagina_planfami(afiliado)
    elems.append(Spacer(1, 6))
    elems.append(Paragraph(
        "Documento generado automáticamente por SIEDFASER — Seguimiento Planificación Familiar",
        STYLE_FOOTER,
    ))
    doc.build(elems)
    return output_path
