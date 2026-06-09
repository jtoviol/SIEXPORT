"""Generador PDF FINDRISC fiel al formato oficial Mutualser/Seragil.

Diseño:
- Banner superior granate con título centrado + logos a los lados
- Sección DATOS GENERALES DEL AFILIADO
- 8 preguntas con opciones marcadas con checkboxes [X] / [ ]
- Recuadro de puntaje total con clasificación de riesgo

Los puntajes individuales se calculan en Python a partir de los datos crudos
del reporte (la SQL nueva solo trae el puntaje_total).
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

from efdi.domain.models import AfiliadoConFindrisc, RegistroFindrisc

# ─── Paleta ──────────────────────────────────────────────────────────────────
COLOR_SECTION      = colors.HexColor("#234674")   # azul institucional secciones
COLOR_QUESTION_BG  = colors.HexColor("#E9EEF5")   # fondo de pregunta
COLOR_ALT_ROW      = colors.HexColor("#F5F7FA")   # alterno claro
COLOR_BORDER       = colors.HexColor("#B0BEC9")
COLOR_TEXT         = colors.HexColor("#1A1A1A")
COLOR_LABEL        = colors.HexColor("#3D4654")
# Marcado (mismo estilo que DI: fondo verde claro + borde verde)
COLOR_MARK_BG      = colors.HexColor("#DCFCE7")
COLOR_MARK_BORDER  = colors.HexColor("#16A34A")
COLOR_MARK_TEXT    = colors.HexColor("#15803D")

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
STYLE_QUESTION = ParagraphStyle(
    "Question", parent=_styles["Normal"],
    fontName="Helvetica-Bold", fontSize=8, textColor=COLOR_TEXT, leading=11,
)
STYLE_OPTION = ParagraphStyle(
    "Option", parent=_styles["Normal"],
    fontName="Helvetica", fontSize=8, textColor=COLOR_TEXT, leading=10,
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


def _raw(v: str | None) -> str:
    """Devuelve el string literal de la BD o '—' si está vacío."""
    if v is None:
        return "—"
    s = str(v).strip()
    return s or "—"


def _option_html(texto: str, marcada: bool) -> str:
    """HTML de UNA opción dentro del recuadro. La marcada va en bold + color verde."""
    if marcada:
        return f'<font color="#15803D"><b>{texto}</b></font>'
    return texto


# ─── Bloques visuales ────────────────────────────────────────────────────────

def _banner(width: float) -> Table:
    """Header limpio: logo Mutualser a la izquierda + título centrado.
    Sin franja de color de fondo. Solo una línea inferior azul."""
    logo_m = Image(str(LOGO_MUTUALSER), width=2.4*cm, height=1.4*cm, kind="proportional") if LOGO_MUTUALSER.exists() else ""
    titulo = Paragraph("SOPORTE ENCUESTAS FINDRISC", STYLE_TITLE)

    # Columna espaciadora del lado derecho para que el título quede visualmente centrado
    t = Table(
        [[logo_m, titulo, ""]],
        colWidths=[2.8*cm, width - 5.6*cm, 2.8*cm],
    )
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


def _datos_generales(
    reg: RegistroFindrisc,
    width: float,
    regimen_override: str | None = None,
) -> Table:
    """Bloque de datos demográficos del afiliado.

    `regimen_override` viene seteado cuando la extracción se filtró por régimen
    (SUBSIDIADO/CONTRIBUTIVO vía AVS_REGISTROS_AP) — manda sobre cualquier valor
    que pudiera traer la BD para garantizar consistencia con el filtro de la query.
    """
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

    doc_full = f"{_sn(reg.tipo_identificacion_desc, reg.tipo_documento)}: {_sn(reg.num_documento)}"
    regimen_str = (regimen_override or "").strip() or "—"

    # Layout: 5 filas de info
    row1 = [cell("Nombre del afiliado", _sn(reg.nombre_completo)),
            cell("Sexo", _sn(reg.sexo))]
    row2 = [cell("Edad actual", f"{reg.edad} años"),
            cell("Documento", doc_full),
            cell("Municipio", _sn(reg.municipio))]
    row3 = [cell("Teléfono 1", _sn(reg.telefono_1)),
            cell("Teléfono 2", _sn(reg.telefono_2)),
            cell("Régimen", regimen_str)]
    row4 = [cell("Correo electrónico", _sn(reg.correo))]
    row5 = [cell("IPS de atención integral a la que se remite", _sn(reg.ips))]

    # Cada fila en su propia tabla de columnas para mejor control
    tablas = []
    for row, widths in [
        (row1, [width * 0.62, width * 0.38]),
        (row2, [width * 0.20, width * 0.42, width * 0.38]),
        (row3, [width * 0.34, width * 0.34, width * 0.32]),
        (row4, [width]),
        (row5, [width]),
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
    # Combinar verticalmente
    contenedor = Table([[t] for t in tablas], colWidths=[width])
    contenedor.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",(0, 0), (-1, -1), 0),
        ("TOPPADDING",  (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    return contenedor


def _pregunta_valor(numero: int, enunciado: str, valor: str, width: float) -> Table:
    """Pregunta sin opciones — solo enunciado + el dato literal de la BD debajo."""
    titulo_html = f"<b>{numero}.</b>  {enunciado}"
    enunciado_p = Paragraph(titulo_html, STYLE_QUESTION)
    valor_html = f'<font size="10"><b>{valor}</b></font>'
    valor_p = Paragraph(valor_html, STYLE_OPTION)

    contenedor = Table(
        [[enunciado_p], [valor_p]],
        colWidths=[width],
    )
    contenedor.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (0, 0), COLOR_QUESTION_BG),
        ("BOX",         (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",(0, 0), (-1, -1), 8),
        ("TOPPADDING",  (0, 0), (0, 0), 3),
        ("BOTTOMPADDING",(0, 0), (0, 0), 3),
        ("TOPPADDING",  (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 1), (-1, -1), 5),
    ]))
    return contenedor


def _pregunta(numero: int, enunciado: str, opciones: list[tuple[str, bool]],
              width: float, extra: str | None = None) -> Table:
    """Bloque de una pregunta: enunciado en header azul + grid de opciones.

    La opción seleccionada va con fondo verde claro + borde verde
    (mismo estilo que las casillas marcadas del PDF de Demanda Inducida).

    opciones = [(texto, marcada), ...]
    """
    titulo_html = f"<b>{numero}.</b>  {enunciado}"
    if extra:
        titulo_html += f"  <font color='#3D4654'>· {extra}</font>"
    enunciado_p = Paragraph(titulo_html, STYLE_QUESTION)

    # 2 columnas — repartimos opciones balanceadas
    n = len(opciones)
    media = (n + 1) // 2
    izq_opts = opciones[:media]
    der_opts = opciones[media:]
    while len(der_opts) < len(izq_opts):
        der_opts.append(None)

    # Construyo la grid de opciones (cada celda es una opción)
    grid_rows: list[list[object]] = []
    marcadas_pos: list[tuple[int, int]] = []   # (row, col) para resaltar luego
    for r, (izq, der) in enumerate(zip(izq_opts, der_opts, strict=False)):
        row_cells: list[object] = []
        for c, opt in enumerate((izq, der)):
            if opt is None:
                row_cells.append("")
                continue
            texto, marcada = opt
            row_cells.append(Paragraph(_option_html(texto, marcada), STYLE_OPTION))
            if marcada:
                marcadas_pos.append((r, c))
        grid_rows.append(row_cells)

    opciones_tabla = Table(grid_rows, colWidths=[width * 0.50, width * 0.50])
    style_cmds = [
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("INNERGRID",    (0, 0), (-1, -1), 0.25, COLOR_BORDER),
        ("BOX",          (0, 0), (-1, -1), 0.4,  COLOR_BORDER),
    ]
    # Resalto la celda elegida: fondo verde + borde verde grueso (estilo DI)
    for (r, c) in marcadas_pos:
        style_cmds.append(("BACKGROUND", (c, r), (c, r), COLOR_MARK_BG))
        style_cmds.append(("BOX",        (c, r), (c, r), 1.2, COLOR_MARK_BORDER))
    opciones_tabla.setStyle(TableStyle(style_cmds))

    contenedor = Table(
        [[enunciado_p], [opciones_tabla]],
        colWidths=[width],
    )
    contenedor.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (0, 0), COLOR_QUESTION_BG),
        ("BOX",         (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",(0, 0), (-1, -1), 0),
        ("TOPPADDING",  (0, 0), (0, 0), 3),
        ("BOTTOMPADDING",(0, 0), (0, 0), 3),
        ("TOPPADDING",  (0, 1), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 1), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (0, 0), 8),   # padding solo en el enunciado
    ]))
    return contenedor


def _cuestionario(reg: RegistroFindrisc, width: float) -> list:
    """Las 8 preguntas FINDRISC.

    Preguntas 1-3 (Edad, IMC, Perímetro) muestran el valor crudo de la BD sin
    marcar ninguna casilla — la BD trae el número, no el rango pre-elegido.
    Preguntas 4-8 marcan la opción que coincide con lo que dice la BD.
    """
    bloques = []

    # 1. Edad — solo el valor literal de la BD
    bloques.append(_pregunta_valor(
        1, "¿Cuál es su edad?",
        f"{reg.edad} años",
        width,
    ))

    # 2. IMC — solo los valores literales de la BD
    bloques.append(_pregunta_valor(
        2, "¿Cuál es su Índice de Masa Corporal (IMC)?",
        f"Peso: {_raw(reg.peso)}   ·   Talla: {_raw(reg.talla)}   ·   IMC: {_raw(reg.imc)}",
        width,
    ))

    # 3. Perímetro cintura — solo el valor literal de la BD
    bloques.append(_pregunta_valor(
        3, "¿Cuál es su perímetro de cintura?",
        f"{_raw(reg.perimetro_cintura)} cm",
        width,
    ))

    # 4. Actividad física
    bloques.append(_pregunta(
        4, "¿Realiza al menos 30 minutos de actividad física cada día?",
        [
            ("Sí", reg.actividad_fisica),
            ("No", not reg.actividad_fisica),
        ],
        width,
    ))

    # 5. Frecuencia verduras
    todos_dias = (reg.frecuencia_verduras or "").upper().startswith("TODOS")
    bloques.append(_pregunta(
        5, "¿Con qué frecuencia come verduras o frutas?",
        [
            ("Todos los días",     todos_dias),
            ("No todos los días",  not todos_dias),
        ],
        width,
    ))

    # 6. Medicamentos hipertensión
    bloques.append(_pregunta(
        6, "¿Ha tomado medicamentos para la presión arterial alta?",
        [
            ("No", not reg.medicamentos_hipertension),
            ("Sí", reg.medicamentos_hipertension),
        ],
        width,
    ))

    # 7. Glucosa alta
    bloques.append(_pregunta(
        7, "¿Se le ha encontrado alguna vez glucosa alta en la sangre?",
        [
            ("No", not reg.glucosa_alta),
            ("Sí", reg.glucosa_alta),
        ],
        width,
    ))

    # 8. Antecedente familiar — match exacto contra el texto que trae la BD
    ant_bd = (reg.antecedente_diabetes or "").strip().upper()
    bloques.append(_pregunta(
        8, "¿Se le ha diagnosticado diabetes (tipo 1 o 2) a alguno de sus familiares?",
        [
            ("No / Otros parientes",                ant_bd == "OTROS PARIENTES O NINGUNO"),
            ("Sí: abuelos, tíos o primos hermanos", ant_bd == "SI ABUELOS O TIOS O PRIMOS HERMANOS"),
            ("Sí: padres o hermanos",               ant_bd == "SI PADRES O HERMANOS"),
        ],
        width,
    ))

    return bloques


def _puntaje_final(reg: RegistroFindrisc, width: float) -> Table:
    """Recuadro final con el puntaje total tal cual viene de la BD."""
    html = (
        f'<font color="#FFFFFF" size="10"><b>Puntaje total</b></font><br/><br/>'
        f'<font color="#FFFFFF" size="22"><b>{reg.puntaje_total}</b></font>'
    )
    parr = Paragraph(html, ParagraphStyle("ptotal", alignment=TA_CENTER, leading=22))

    t = Table([[parr]], colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), COLOR_SECTION),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING",   (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 12),
    ]))
    return t


# ─── Composición del documento ────────────────────────────────────────────────

def _construir_pagina_findrisc(
    afiliado: AfiliadoConFindrisc,
    regimen_override: str | None = None,
) -> list:
    reg = afiliado.registros[0]   # un registro por afiliado por día
    # ancho usable: letter (612pt) - márgenes (10mm c/u)
    width = letter[0] - 20 * mm

    elems = []
    elems.append(_banner(width))
    elems.append(Spacer(1, 4))

    elems.append(_section_header("DATOS GENERALES DEL AFILIADO", width))
    elems.append(_datos_generales(reg, width, regimen_override=regimen_override))
    elems.append(Spacer(1, 4))

    elems.append(_section_header("CUESTIONARIO FINDRISC", width))
    elems.append(Spacer(1, 2))
    for bloque in _cuestionario(reg, width):
        elems.append(bloque)
        elems.append(Spacer(1, 2))

    elems.append(Spacer(1, 4))
    elems.append(_puntaje_final(reg, width))

    return elems


def generar_pdf_findrisc(
    afiliado: AfiliadoConFindrisc,
    output_path: Path,
    regimen_override: str | None = None,
) -> Path:
    """Genera el PDF FINDRISC.

    `regimen_override` se popula desde el job cuando la extracción se filtró
    por régimen — se imprime en el bloque de datos generales para que el soporte
    deje claro a qué régimen pertenece la encuesta.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=10*mm, rightMargin=10*mm,
        topMargin=8*mm, bottomMargin=8*mm,
        title=f"FINDRISC — {afiliado.pdf_key}",
        author="SIEDFASER",
    )
    elems = _construir_pagina_findrisc(afiliado, regimen_override=regimen_override)
    elems.append(Spacer(1, 6))
    elems.append(Paragraph(
        "Documento generado automáticamente por SIEDFASER — Evaluación de Riesgo FINDRISC",
        STYLE_FOOTER,
    ))
    doc.build(elems)
    return output_path
