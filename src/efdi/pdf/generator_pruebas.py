"""Generador PDF Pruebas Rápidas — 1 PDF por respuesta de prueba.

Layout:
- Banner superior con logo Mutualser + título
- DATOS GENERALES DEL AFILIADO (mismo estilo que FINDRISC)
- RESULTADO DE LA PRUEBA (nombre, fecha, resultado destacado, lote, observación)
- DATOS DEL ENCUESTADOR

Una persona puede tener N PDFs en su carpeta (uno por cada prueba que se hizo
en el periodo). Régimen viene del `regimen_override` declarado por el usuario
al lanzar el job — no se lee de la BD.
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

from efdi.domain.models import RespuestaPruebaRapida

# ─── Paleta ──────────────────────────────────────────────────────────────────
COLOR_SECTION      = colors.HexColor("#234674")
COLOR_QUESTION_BG  = colors.HexColor("#E9EEF5")
COLOR_BORDER       = colors.HexColor("#B0BEC9")
COLOR_TEXT         = colors.HexColor("#1A1A1A")
COLOR_LABEL        = colors.HexColor("#3D4654")
COLOR_RESULT_POS_BG     = colors.HexColor("#FEE2E2")     # rojo claro
COLOR_RESULT_POS_BORDER = colors.HexColor("#B91C1C")
COLOR_RESULT_POS_TEXT   = colors.HexColor("#7F1D1D")
COLOR_RESULT_NEG_BG     = colors.HexColor("#DCFCE7")     # verde claro
COLOR_RESULT_NEG_BORDER = colors.HexColor("#16A34A")
COLOR_RESULT_NEG_TEXT   = colors.HexColor("#15803D")
COLOR_RESULT_OTHER_BG   = colors.HexColor("#FEF3C7")     # ámbar (indeterminado / sin parseo)
COLOR_RESULT_OTHER_BORDER = colors.HexColor("#D97706")
COLOR_RESULT_OTHER_TEXT = colors.HexColor("#92400E")

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
STYLE_PRUEBA_NOMBRE = ParagraphStyle(
    "PruebaNombre", parent=_styles["Normal"],
    fontName="Helvetica-Bold", fontSize=12, textColor=COLOR_SECTION,
    alignment=TA_CENTER, leading=14,
)
STYLE_RESULTADO = ParagraphStyle(
    "Resultado", parent=_styles["Normal"],
    fontName="Helvetica-Bold", fontSize=16, alignment=TA_CENTER, leading=20,
)
STYLE_FOOTER = ParagraphStyle(
    "Footer", parent=_styles["Normal"],
    fontName="Helvetica-Oblique", fontSize=6, textColor=colors.grey,
    alignment=TA_CENTER,
)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _sn(v: object, default: str = "—") -> str:
    s = str(v).strip() if v is not None else ""
    return s or default


def _cell(label: str, value: str) -> Table:
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


# ─── Bloques visuales ────────────────────────────────────────────────────────

def _banner(width: float) -> Table:
    logo_m = Image(str(LOGO_MUTUALSER), width=2.4*cm, height=1.4*cm, kind="proportional") if LOGO_MUTUALSER.exists() else ""
    titulo = Paragraph("SOPORTE PRUEBAS RÁPIDAS", STYLE_TITLE)
    t = Table([[logo_m, titulo, ""]], colWidths=[2.8*cm, width - 5.6*cm, 2.8*cm])
    t.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",       (0, 0), (0, 0),   "LEFT"),
        ("ALIGN",       (1, 0), (1, 0),   "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",(0, 0), (-1, -1), 0),
        ("TOPPADDING",  (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
        ("LINEBELOW",   (0, 0), (-1, -1), 1, COLOR_SECTION),
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


def _datos_generales(reg: RespuestaPruebaRapida, width: float, regimen_override: str | None) -> Table:
    doc_full = f"{_sn(reg.tipo_identificacion_desc, str(reg.tipo_documento))}: {_sn(reg.num_documento)}"
    regimen_str = (regimen_override or "").strip() or "—"
    gestante_str = "SI" if reg.flg_gestante else "NO"

    row1 = [_cell("Nombre del afiliado", _sn(reg.nombre_completo)),
            _cell("Sexo", _sn(reg.sexo))]
    row2 = [_cell("Edad actual", f"{reg.edad} años"),
            _cell("Documento", doc_full),
            _cell("Régimen", regimen_str)]
    row3 = [_cell("Departamento", _sn(reg.departamento)),
            _cell("Municipio", _sn(reg.municipio)),
            _cell("Gestante", gestante_str)]
    row4 = [_cell("Dirección", _sn(reg.direccion))]
    row5 = [_cell("Teléfono 1", _sn(reg.telefono_1)),
            _cell("Teléfono 2", _sn(reg.telefono_2)),
            _cell("Correo electrónico", _sn(reg.correo))]

    tablas = []
    for row, widths in [
        (row1, [width * 0.62, width * 0.38]),
        (row2, [width * 0.20, width * 0.42, width * 0.38]),
        (row3, [width * 0.34, width * 0.34, width * 0.32]),
        (row4, [width]),
        (row5, [width * 0.30, width * 0.30, width * 0.40]),
    ]:
        t = Table([row], colWidths=widths)
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


def _resultado_styles(resultado: str | None) -> tuple[colors.Color, colors.Color, colors.Color]:
    """Devuelve (bg, border, text) según resultado."""
    if not resultado:
        return COLOR_RESULT_OTHER_BG, COLOR_RESULT_OTHER_BORDER, COLOR_RESULT_OTHER_TEXT
    r = resultado.upper()
    if "POSITIV" in r or r in ("PO", "REACTIV"):
        return COLOR_RESULT_POS_BG, COLOR_RESULT_POS_BORDER, COLOR_RESULT_POS_TEXT
    if "NEGATIV" in r or r in ("NE", "NO REACTIV"):
        return COLOR_RESULT_NEG_BG, COLOR_RESULT_NEG_BORDER, COLOR_RESULT_NEG_TEXT
    return COLOR_RESULT_OTHER_BG, COLOR_RESULT_OTHER_BORDER, COLOR_RESULT_OTHER_TEXT


def _bloque_prueba(reg: RespuestaPruebaRapida, width: float) -> Table:
    """Nombre de la prueba arriba grande + cuadro de resultado destacado +
    fila con fecha, lote y presión arterial + observación al pie."""
    nombre = Paragraph(_sn(reg.des_prueba_rapida), STYLE_PRUEBA_NOMBRE)

    bg, border, text_color = _resultado_styles(reg.resultado_prueba)
    resultado_text = _sn(reg.resultado_prueba, "SIN RESULTADO").upper()
    # reportlab acepta "#RRGGBB"; hexval() devuelve "0xRRGGBB" → reemplazo prefijo
    color_hex = "#" + text_color.hexval()[2:]
    resultado_html = f'<font color="{color_hex}">{resultado_text}</font>'
    resultado_p = Paragraph(resultado_html, STYLE_RESULTADO)
    cuadro_res = Table([[resultado_p]], colWidths=[width])
    cuadro_res.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), bg),
        ("BOX",          (0, 0), (-1, -1), 1.5, border),
        ("TOPPADDING",   (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 14),
    ]))

    fila_datos = [
        _cell("Fecha realización", reg.fecha_realizacion.isoformat()),
        _cell("Número de lote", _sn(reg.nro_lote)),
        _cell("Presión arterial", _sn(reg.presion_arterial)),
    ]
    t_datos = Table([fila_datos], colWidths=[width * 0.34, width * 0.33, width * 0.33])
    t_datos.setStyle(TableStyle([
        ("BOX",         (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID",   (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",(0, 0), (-1, -1), 0),
        ("TOPPADDING",  (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))

    obs = _cell("Observación", _sn(reg.observacion))
    t_obs = Table([[obs]], colWidths=[width])
    t_obs.setStyle(TableStyle([
        ("BOX",         (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",(0, 0), (-1, -1), 0),
        ("TOPPADDING",  (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))

    contenedor = Table(
        [[nombre], [cuadro_res], [t_datos], [t_obs]],
        colWidths=[width],
    )
    contenedor.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",(0, 0), (-1, -1), 0),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]))
    return contenedor


def _datos_encuestador(reg: RespuestaPruebaRapida, width: float) -> Table:
    row1 = [_cell("Encuestador", _sn(reg.encuestador)),
            _cell("Cargo", _sn(reg.cargo_encuestador))]
    fecha_reg = reg.fecha_registro.isoformat() if reg.fecha_registro else "—"
    row2 = [_cell("Fecha de registro de la información", fecha_reg)]

    tablas = []
    for row, widths in [
        (row1, [width * 0.55, width * 0.45]),
        (row2, [width]),
    ]:
        t = Table([row], colWidths=widths)
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


# ─── Entrada principal ───────────────────────────────────────────────────────

def generar_pdf_pruebas(
    reg: RespuestaPruebaRapida,
    output: Path,
    regimen_override: str | None = None,
) -> Path:
    """Genera 1 PDF para una respuesta de prueba rápida."""
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output),
        pagesize=letter,
        leftMargin=12*mm, rightMargin=12*mm,
        topMargin=10*mm, bottomMargin=10*mm,
        title=f"Prueba rápida — {reg.des_prueba_rapida} — {reg.num_documento}",
    )
    width = doc.width

    story = [
        _banner(width),
        Spacer(1, 6),
        _section_header("DATOS GENERALES DEL AFILIADO", width),
        _datos_generales(reg, width, regimen_override),
        Spacer(1, 8),
        _section_header("PRUEBA REALIZADA", width),
        _bloque_prueba(reg, width),
        Spacer(1, 8),
        _section_header("DATOS DEL ENCUESTADOR", width),
        _datos_encuestador(reg, width),
        Spacer(1, 6),
        Paragraph(
            "Documento de soporte generado por SIEDFASER · uso administrativo, sin valor diagnóstico",
            STYLE_FOOTER,
        ),
    ]
    doc.build(story)
    return output
