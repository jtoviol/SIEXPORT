"""Generador PDF para evaluación de riesgo FINDRISC.

Produce un PDF por afiliado (1 página landscape) con:
- Datos demográficos completos
- Mediciones antropométricas
- Cuestionario FINDRISC con respuestas resaltadas
- Tabla de puntajes individuales y total
- Resultado con clasificación de riesgo y color indicativo
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import landscape, letter
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

from efdi.domain.models import AfiliadoConFindrisc, RegistroFindrisc

# Paleta (misma que demanda inducida para coherencia visual)
COLOR_PRIMARY   = colors.HexColor("#1A4480")
COLOR_SECONDARY = colors.HexColor("#5A8FCC")
COLOR_LABEL_BG  = colors.HexColor("#F0F4FA")
COLOR_BORDER    = colors.HexColor("#B0BEC9")
COLOR_TEXT      = colors.HexColor("#1A1A1A")

# Colores de riesgo FINDRISC
COLOR_RIESGO = {
    "BAJO":                    colors.HexColor("#16A34A"),
    "LIGERAMENTE ELEVADO":     colors.HexColor("#CA8A04"),
    "MODERADO":                colors.HexColor("#EA580C"),
    "ALTO":                    colors.HexColor("#DC2626"),
    "MUY ALTO":                colors.HexColor("#7F1D1D"),
}
COLOR_RIESGO_BG = {
    "BAJO":                    colors.HexColor("#DCFCE7"),
    "LIGERAMENTE ELEVADO":     colors.HexColor("#FEF9C3"),
    "MODERADO":                colors.HexColor("#FFEDD5"),
    "ALTO":                    colors.HexColor("#FEE2E2"),
    "MUY ALTO":                colors.HexColor("#FEE2E2"),
}

LOGO_PATH = Path(__file__).parent.parent / "templates" / "logo.png"

_styles = getSampleStyleSheet()

STYLE_SECTION = ParagraphStyle(
    "Section", parent=_styles["Heading2"],
    fontName="Helvetica-Bold", fontSize=8, textColor=colors.white,
    backColor=COLOR_PRIMARY, leftIndent=6, spaceBefore=3, spaceAfter=2,
    borderPadding=3,
)
STYLE_FOOTER = ParagraphStyle(
    "Footer", parent=_styles["Normal"],
    fontName="Helvetica-Oblique", fontSize=6, textColor=colors.grey,
    alignment=TA_CENTER,
)
STYLE_NORMAL_SM = ParagraphStyle(
    "NormalSm", parent=_styles["Normal"],
    fontName="Helvetica", fontSize=7, textColor=COLOR_TEXT, leading=9,
)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _sn(v: object, default: str = "—") -> str:
    """Safe string: None → default."""
    s = str(v).strip() if v is not None else ""
    return s or default


def _fmt_float(v: float | None, decimales: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v:.{decimales}f}"


def _clasificar_riesgo(puntaje: int) -> tuple[str, str, str]:
    """Retorna (nivel, porcentaje_riesgo, recomendacion)."""
    if puntaje <= 6:
        return "BAJO",                "~1%",  "Mantener hábitos saludables"
    if puntaje <= 11:
        return "LIGERAMENTE ELEVADO", "~4%",  "Mejorar estilo de vida"
    if puntaje <= 14:
        return "MODERADO",            "~17%", "Consulta médica recomendada"
    if puntaje <= 20:
        return "ALTO",                "~33%", "Se recomienda prueba de glucosa"
    return "MUY ALTO",                "~50%", "Prueba de tolerancia a la glucosa urgente"


def _label_val_table(rows: list[tuple[str, str]], col_widths: tuple | None = None) -> Table:
    """Tabla 4 columnas (etiqueta/valor × 2 por fila)."""
    pairs: list[list] = []
    buf: list = []
    for label, value in rows:
        buf.extend([label, value or "—"])
        if len(buf) == 4:
            pairs.append(buf)
            buf = []
    if buf:
        while len(buf) < 4:
            buf.append("")
        pairs.append(buf)

    widths = col_widths or (2.5*cm, 5.5*cm, 2.5*cm, 5.5*cm)
    t = Table(pairs, colWidths=list(widths))
    t.setStyle(TableStyle([
        ("FONT",         (0, 0), (-1, -1), "Helvetica",      7),
        ("FONT",         (0, 0), (0, -1),  "Helvetica-Bold", 7),
        ("FONT",         (2, 0), (2, -1),  "Helvetica-Bold", 7),
        ("TEXTCOLOR",    (0, 0), (0, -1),  COLOR_PRIMARY),
        ("TEXTCOLOR",    (2, 0), (2, -1),  COLOR_PRIMARY),
        ("BACKGROUND",   (0, 0), (0, -1),  COLOR_LABEL_BG),
        ("BACKGROUND",   (2, 0), (2, -1),  COLOR_LABEL_BG),
        ("BOX",          (0, 0), (-1, -1), 0.4, COLOR_BORDER),
        ("INNERGRID",    (0, 0), (-1, -1), 0.2, COLOR_BORDER),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",   (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _header_table(afiliado: AfiliadoConFindrisc, reg: RegistroFindrisc) -> Table:
    logo_cell = ""
    if LOGO_PATH.exists():
        try:
            logo_cell = Image(str(LOGO_PATH), width=2.0*cm, height=1.2*cm, kind="proportional")
        except Exception:
            pass

    titulo_html = (
        "<para alignment='center'>"
        "<font name='Helvetica-Bold' size='11' color='#1A4480'>EVALUACIÓN DE RIESGO FINDRISC</font><br/>"
        "<font name='Helvetica' size='6.5' color='#5A8FCC'>"
        "Finnish Diabetes Risk Score — Tamizaje de Riesgo de Diabetes Tipo 2"
        "</font></para>"
    )
    info_html = (
        f"<para alignment='right'>"
        f"<font name='Helvetica-Bold' size='8' color='#1A4480'>"
        f"{reg.tipo_documento} {reg.num_documento}</font><br/>"
        f"<font name='Helvetica' size='6.5' color='#94A3B8'>"
        f"Realizado: {_sn(reg.fecha_realizacion)}  ·  Registro: {_sn(reg.fecha_registro)}"
        f"</font></para>"
    )

    data = [[logo_cell, Paragraph(titulo_html, _styles["Normal"]), Paragraph(info_html, _styles["Normal"])]]
    t = Table(data, colWidths=[2.4*cm, 18*cm, 5.5*cm])
    t.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LINEBELOW",    (0, 0), (-1, -1), 0.75, COLOR_PRIMARY),
    ]))
    return t


def _mediciones_table(reg: RegistroFindrisc) -> Table:
    def _imc_clasificacion(imc: float | None) -> str:
        if imc is None: return ""
        if imc < 18.5:  return " (Bajo peso)"
        if imc < 25:    return " (Normal)"
        if imc < 30:    return " (Sobrepeso)"
        return " (Obesidad)"

    imc_cls = _imc_clasificacion(reg.imc)
    rows = [
        ["Peso",               f"{_fmt_float(reg.peso)} kg"],
        ["Talla",              f"{_fmt_float(reg.talla, 2)} m"],
        ["IMC",                f"{_fmt_float(reg.imc)}{imc_cls}"],
        ["Prim. abdominal",    f"{_fmt_float(reg.perimetro_cintura)} cm"],
    ]
    data = [[r[0], r[1]] for r in rows]
    t = Table(data, colWidths=[3.0*cm, 5.0*cm])
    t.setStyle(TableStyle([
        ("FONT",         (0, 0), (-1, -1), "Helvetica",      7),
        ("FONT",         (0, 0), (0, -1),  "Helvetica-Bold", 7),
        ("TEXTCOLOR",    (0, 0), (0, -1),  COLOR_PRIMARY),
        ("BACKGROUND",   (0, 0), (0, -1),  COLOR_LABEL_BG),
        ("BOX",          (0, 0), (-1, -1), 0.4, COLOR_BORDER),
        ("INNERGRID",    (0, 0), (-1, -1), 0.2, COLOR_BORDER),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",   (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _cuestionario_table(reg: RegistroFindrisc) -> Table:
    def _yesno(v: bool, pts_si: int, pts_no: int = 0) -> tuple[str, int]:
        return ("SÍ", pts_si) if v else ("NO", pts_no)

    def _freq_v(v: str | None) -> tuple[str, int]:
        if v and "TODOS" in v:
            return ("TODOS LOS DÍAS", 0)
        return ("NO TODOS LOS DÍAS", 1)

    def _diab(v: str | None) -> tuple[str, int]:
        if not v or "NINGUNO" in v:
            return ("NINGUNO / OTROS PARIENTES", 0)
        if "PADRES" in v or "HERMANOS" in v:
            return ("PADRES O HERMANOS", 5)
        return ("ABUELOS / TÍOS / PRIMOS", 3)

    activ_resp, activ_pts = _yesno(reg.actividad_fisica, 0, 2)
    verd_resp,  verd_pts  = _freq_v(reg.frecuencia_verduras)
    med_resp,   med_pts   = _yesno(reg.medicamentos_hipertension, 2, 0)
    gluc_resp,  gluc_pts  = _yesno(reg.glucosa_alta, 5, 0)
    diab_resp,  diab_pts  = _diab(reg.antecedente_diabetes)
    aplica_resp, _        = _yesno(reg.aplica_prueba, 1, 0)

    encabezado = ["Pregunta FINDRISC", "Respuesta", "Pts"]
    filas = [
        encabezado,
        ["¿Practica actividad física ≥ 30 min/día o trabajo físico intenso?", activ_resp, str(activ_pts)],
        ["¿Consume verduras, frutas o bayas todos los días?",                  verd_resp,  str(verd_pts)],
        ["¿Toma medicamentos para la hipertensión arterial?",                  med_resp,   str(med_pts)],
        ["¿Le han encontrado glucosa alta alguna vez?",                        gluc_resp,  str(gluc_pts)],
        ["¿Familiares diagnosticados con diabetes tipo 1 o 2?",               diab_resp,  str(diab_pts)],
        ["¿Aplica para prueba diagnóstica?",                                   aplica_resp, "—"],
    ]

    col_w = [10.5*cm, 4.5*cm, 1.0*cm]
    t = Table(filas, colWidths=col_w, repeatRows=1)

    style_cmds = [
        ("FONT",         (0, 0), (-1, 0),  "Helvetica-Bold", 7),
        ("FONT",         (0, 1), (-1, -1), "Helvetica",      7),
        ("BACKGROUND",   (0, 0), (-1, 0),  COLOR_PRIMARY),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.white),
        ("BOX",          (0, 0), (-1, -1), 0.4, COLOR_BORDER),
        ("INNERGRID",    (0, 0), (-1, -1), 0.2, COLOR_BORDER),
        ("ALIGN",        (1, 0), (2, -1),  "CENTER"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    # Resaltar filas con respuesta afirmativa significativa
    respuestas_positivas = {
        1: (activ_resp == "NO"),
        2: (verd_resp != "TODOS LOS DÍAS"),
        3: (med_resp == "SÍ"),
        4: (gluc_resp == "SÍ"),
        5: (diab_resp != "NINGUNO / OTROS PARIENTES"),
    }
    for row_i, positivo in respuestas_positivas.items():
        if positivo:
            style_cmds.append(("BACKGROUND", (1, row_i), (2, row_i), colors.HexColor("#FEE2E2")))
        else:
            style_cmds.append(("BACKGROUND", (1, row_i), (2, row_i), colors.HexColor("#DCFCE7")))

    t.setStyle(TableStyle(style_cmds))
    return t


def _puntajes_table(reg: RegistroFindrisc) -> Table:
    nivel, porcentaje, _ = _clasificar_riesgo(reg.puntaje_total)
    color_nivel = COLOR_RIESGO.get(nivel, COLOR_PRIMARY)
    color_bg    = COLOR_RIESGO_BG.get(nivel, COLOR_LABEL_BG)

    encabezado = ["Criterio", "Edad", "IMC", "P. abdom.", "Act. física", "Verduras", "Medicam.", "Glucosa", "Antec. diab.", "TOTAL"]
    valores = [
        "Puntaje",
        str(reg.puntaje_edad),
        str(reg.puntaje_imc),
        str(reg.puntaje_perimetro),
        str(reg.puntaje_actividad_fisica),
        str(reg.puntaje_verduras),
        str(reg.puntaje_medicamentos),
        str(reg.puntaje_glucosa),
        str(reg.puntaje_diabetes),
        str(reg.puntaje_total),
    ]

    filas = [encabezado, valores]
    col_w = [2.0*cm] + [1.8*cm] * 8 + [1.8*cm]
    t = Table(filas, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONT",         (0, 0), (-1, 0),  "Helvetica-Bold", 7),
        ("FONT",         (0, 1), (-1, -1), "Helvetica",      8),
        ("BACKGROUND",   (0, 0), (-1, 0),  COLOR_PRIMARY),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.white),
        ("BACKGROUND",   (9, 1), (9, 1),   color_bg),
        ("TEXTCOLOR",    (9, 1), (9, 1),   color_nivel),
        ("FONT",         (9, 1), (9, 1),   "Helvetica-Bold", 10),
        ("BOX",          (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID",    (0, 0), (-1, -1), 0.2, COLOR_BORDER),
        ("BOX",          (9, 1), (9, 1),   1.0, color_nivel),
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
    ]))
    return t


def _resultado_table(reg: RegistroFindrisc) -> Table:
    nivel, porcentaje, recomendacion = _clasificar_riesgo(reg.puntaje_total)
    color_nivel = COLOR_RIESGO.get(nivel, COLOR_PRIMARY)
    color_bg    = COLOR_RIESGO_BG.get(nivel, COLOR_LABEL_BG)

    puntaje_html = (
        f"<para alignment='center'>"
        f"<font name='Helvetica-Bold' size='22' color='{color_nivel.hexval()}'>"
        f"{reg.puntaje_total}</font><br/>"
        f"<font name='Helvetica' size='6.5' color='#64748B'>puntos</font>"
        f"</para>"
    )
    nivel_html = (
        f"<para alignment='center'>"
        f"<font name='Helvetica-Bold' size='10' color='{color_nivel.hexval()}'>"
        f"RIESGO {nivel}</font><br/>"
        f"<font name='Helvetica' size='7.5' color='#64748B'>"
        f"Riesgo estimado de DM2: {porcentaje}</font><br/>"
        f"<font name='Helvetica-Oblique' size='7' color='#94A3B8'>"
        f"{recomendacion}</font>"
        f"</para>"
    )

    aplica_html = (
        f"<para alignment='center'>"
        f"<font name='Helvetica-Bold' size='7.5' color='{COLOR_PRIMARY.hexval()}'>"
        f"{'✓ APLICA PARA PRUEBA' if reg.aplica_prueba else '✗ NO APLICA PARA PRUEBA'}"
        f"</font></para>"
    )

    data = [[
        Paragraph(puntaje_html, _styles["Normal"]),
        Paragraph(nivel_html,   _styles["Normal"]),
        Paragraph(aplica_html,  _styles["Normal"]),
    ]]
    t = Table(data, colWidths=[3.0*cm, 11.0*cm, 4.0*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (1, 0),   color_bg),
        ("BACKGROUND",   (2, 0), (2, 0),   COLOR_LABEL_BG),
        ("BOX",          (0, 0), (-1, -1), 1.0, color_nivel),
        ("INNERGRID",    (0, 0), (-1, -1), 0.4, color_nivel),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _construir_pagina_findrisc(afiliado: AfiliadoConFindrisc) -> list:
    """Arma los flowables para UN registro FINDRISC (usa el primero del grupo)."""
    reg = afiliado.registros[0]
    elems: list = []

    # Cabecera
    elems.append(_header_table(afiliado, reg))
    elems.append(Spacer(1, 4))

    # Datos del paciente
    elems.append(Paragraph("DATOS DEL PACIENTE", STYLE_SECTION))
    elems.append(_label_val_table([
        ("Nombre",         afiliado.nombre_completo),
        ("Documento",      f"{reg.tipo_documento} {reg.num_documento}"),
        ("Fecha nac.",     _sn(reg.fecha_nacimiento)),
        ("Edad",           f"{reg.edad} años"),
        ("Género",         _sn(reg.genero)),
        ("Curso de vida",  _sn(reg.curso_vida)),
        ("Régimen",        _sn(reg.regimen)),
        ("Dirección",      _sn(reg.direccion)),
        ("Teléfono",       _sn(reg.telefono_1)),
        ("Correo",         _sn(reg.correo)),
        ("Depto / Mun.",   f"{_sn(reg.departamento, '')} / {_sn(reg.municipio, '')}".strip(" /") or "—"),
        ("Regional",       _sn(reg.regional)),
    ]))
    elems.append(Spacer(1, 3))

    # Encuestador + IPS (fila compacta)
    elems.append(Paragraph("ENCUESTADOR E IPS", STYLE_SECTION))
    elems.append(_label_val_table([
        ("Encuestador", _sn(reg.encuestador_nombre)),
        ("Cargo",       _sn(reg.cargo_encuestador)),
        ("IPS",         _sn(reg.ips)),
        ("SEQ SERAGIL", str(reg.seq_seragil)),
    ]))
    elems.append(Spacer(1, 3))

    # Mediciones + Cuestionario en 2 columnas
    mediciones_block = [
        Paragraph("MEDICIONES ANTROPOMÉTRICAS", STYLE_SECTION),
        _mediciones_table(reg),
    ]
    cuestionario_block = [
        Paragraph("CUESTIONARIO FINDRISC", STYLE_SECTION),
        _cuestionario_table(reg),
    ]

    from reportlab.platypus import KeepTogether
    dos_col = Table(
        [[mediciones_block, cuestionario_block]],
        colWidths=[8.5*cm, 17.5*cm],
    )
    dos_col.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    elems.append(dos_col)
    elems.append(Spacer(1, 3))

    # Puntajes
    elems.append(Paragraph("PUNTUACIÓN FINDRISC", STYLE_SECTION))
    elems.append(_puntajes_table(reg))
    elems.append(Spacer(1, 4))

    # Resultado
    elems.append(Paragraph("RESULTADO", STYLE_SECTION))
    elems.append(_resultado_table(reg))

    return elems


def generar_pdf_findrisc(afiliado: AfiliadoConFindrisc, output_path: Path) -> Path:
    """Genera UN PDF por afiliado con la evaluación FINDRISC completa."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(letter),
        leftMargin=10*mm, rightMargin=10*mm,
        topMargin=8*mm, bottomMargin=8*mm,
        title=f"FINDRISC — {afiliado.pdf_key}",
        author="SIEDFASER",
    )
    elems = _construir_pagina_findrisc(afiliado)
    elems.append(Spacer(1, 6))
    elems.append(Paragraph(
        "Documento generado automáticamente por SIEDFASER — Evaluación de Riesgo FINDRISC",
        STYLE_FOOTER,
    ))
    doc.build(elems)
    return output_path
