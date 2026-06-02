"""Generador de PDFs por afiliado — multi-página con catálogo de programas.

Cada PDF representa UN afiliado y contiene N páginas (una por atención).
Cada página marca con ☒ la casilla del programa correspondiente y deja en ☐
los otros 123 del catálogo.
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from efdi.domain.models import AfiliadoConAtenciones, Atencion
from efdi.pdf.programas_catalogo import cargar_catalogo

# Paleta
COLOR_PRIMARY = colors.HexColor("#1A4480")
COLOR_SECONDARY = colors.HexColor("#5A8FCC")
COLOR_LABEL_BG = colors.HexColor("#F0F4FA")
COLOR_BORDER = colors.HexColor("#B0BEC9")
COLOR_TEXT = colors.HexColor("#1A1A1A")
COLOR_MARK_BG = colors.HexColor("#DCFCE7")  # verde claro para casilla marcada
COLOR_MARK_BORDER = colors.HexColor("#16A34A")

LOGO_PATH = Path(__file__).parent.parent / "templates" / "logo.png"

# Estilos
_styles = getSampleStyleSheet()
STYLE_TITLE = ParagraphStyle(
    "Title", parent=_styles["Title"],
    fontName="Helvetica-Bold", fontSize=13, textColor=COLOR_PRIMARY,
    spaceAfter=2, alignment=TA_CENTER, leading=15,
)
STYLE_SUBTITLE = ParagraphStyle(
    "Subtitle", parent=_styles["Normal"],
    fontName="Helvetica", fontSize=7.5, textColor=COLOR_SECONDARY,
    alignment=TA_CENTER, spaceAfter=4,
)
STYLE_SECTION = ParagraphStyle(
    "Section", parent=_styles["Heading2"],
    fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.white,
    backColor=COLOR_PRIMARY, leftIndent=6, spaceBefore=4, spaceAfter=2,
    borderPadding=3,
)
STYLE_FOOTER = ParagraphStyle(
    "Footer", parent=_styles["Normal"],
    fontName="Helvetica-Oblique", fontSize=6.5, textColor=colors.grey,
    alignment=TA_CENTER,
)
STYLE_PROG_NORMAL = ParagraphStyle(
    "ProgNormal", parent=_styles["Normal"],
    fontName="Helvetica", fontSize=6.5, textColor=COLOR_TEXT,
    leading=8, leftIndent=0,
)
STYLE_PROG_MARKED = ParagraphStyle(
    "ProgMarked", parent=_styles["Normal"],
    fontName="Helvetica-Bold", fontSize=6.5, textColor=COLOR_PRIMARY,
    leading=8, leftIndent=0,
)


def _label_value_table(rows: list[tuple[str, str]], col_widths: tuple[float, ...] | None = None) -> Table:
    """Tabla de 4 columnas (2 pares etiqueta/valor por fila)."""
    pairs: list[list[str]] = []
    buf: list[str] = []
    for label, value in rows:
        buf.extend([label, value or "—"])
        if len(buf) == 4:
            pairs.append(buf)
            buf = []
    if buf:
        while len(buf) < 4:
            buf.append("")
        pairs.append(buf)

    widths = col_widths or (2.8*cm, 6.5*cm, 2.8*cm, 6.5*cm)
    t = Table(pairs, colWidths=list(widths))
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 7.5),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 7.5),
        ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 7.5),
        ("TEXTCOLOR", (0, 0), (0, -1), COLOR_PRIMARY),
        ("TEXTCOLOR", (2, 0), (2, -1), COLOR_PRIMARY),
        ("TEXTCOLOR", (1, 0), (1, -1), COLOR_TEXT),
        ("TEXTCOLOR", (3, 0), (3, -1), COLOR_TEXT),
        ("BACKGROUND", (0, 0), (0, -1), COLOR_LABEL_BG),
        ("BACKGROUND", (2, 0), (2, -1), COLOR_LABEL_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, COLOR_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _header_table(afiliado: AfiliadoConAtenciones, atencion: Atencion, page_n: int, page_total: int) -> Table:
    """Cabecera con logo a la izquierda + título centro + contador derecha."""
    logo_cell = ""
    if LOGO_PATH.exists():
        try:
            logo_cell = Image(str(LOGO_PATH), width=2.2*cm, height=1.3*cm, kind="proportional")
        except Exception:
            logo_cell = ""

    titulo_html = (
        f"<para alignment='center'>"
        f"<font name='Helvetica-Bold' size='12' color='#1A4480'>REGISTRO DE DEMANDA INDUCIDA</font><br/>"
        f"<font name='Helvetica' size='7' color='#5A8FCC'>"
        f"{afiliado.tipo_documento} {afiliado.num_documento} · {afiliado.nombre_completo}"
        f"</font></para>"
    )
    contador_html = (
        f"<para alignment='right'>"
        f"<font name='Helvetica-Bold' size='9' color='#1A4480'>Atención {page_n} de {page_total}</font><br/>"
        f"<font name='Helvetica' size='6.5' color='#94A3B8'>"
        f"Consecutivo {atencion.consecutivo} · SEQ {atencion.seq_seragil}"
        f"</font></para>"
    )

    data = [[logo_cell, Paragraph(titulo_html, _styles["Normal"]), Paragraph(contador_html, _styles["Normal"])]]
    t = Table(data, colWidths=[2.6*cm, 19*cm, 4.5*cm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.75, COLOR_PRIMARY),
    ]))
    return t


def _flags_table(atencion: Atencion) -> Table:
    """Tabla compacta con los 3 flags booleanos."""
    def mark(v: bool) -> str:
        return "✓" if v else "—"

    data = [[
        "Notificación obligatoria", mark(atencion.notificacion_obligatoria),
        "Rec. urgencias", mark(atencion.recuperacion_urgencias),
        "Rec. consulta externa", mark(atencion.recuperacion_consulta_externa),
    ]]
    t = Table(data, colWidths=[4.5*cm, 1.2*cm, 3.5*cm, 1.2*cm, 4.5*cm, 1.2*cm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 7),
        ("FONT", (1, 0), (1, 0), "Helvetica-Bold", 9),
        ("FONT", (3, 0), (3, 0), "Helvetica-Bold", 9),
        ("FONT", (5, 0), (5, 0), "Helvetica-Bold", 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), COLOR_PRIMARY),
        ("TEXTCOLOR", (1, 0), (1, 0),
         colors.green if atencion.notificacion_obligatoria else colors.grey),
        ("TEXTCOLOR", (3, 0), (3, 0),
         colors.green if atencion.recuperacion_urgencias else colors.grey),
        ("TEXTCOLOR", (5, 0), (5, 0),
         colors.green if atencion.recuperacion_consulta_externa else colors.grey),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, COLOR_BORDER),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("ALIGN", (3, 0), (3, 0), "CENTER"),
        ("ALIGN", (5, 0), (5, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    return t


def _programas_table(codigos_marcados: list[str]) -> Table:
    """Tabla de 4 columnas con los 124 programas del catálogo.

    Marca con ☒ + fondo verde todos los códigos en codigos_marcados.
    """
    catalogo = cargar_catalogo()
    if not catalogo:
        return Table([["Catálogo de programas no disponible"]])

    marcados = set(codigos_marcados)
    items = []
    for cod, desc in catalogo:
        es_marcado = cod in marcados
        cuadro = "☒" if es_marcado else "☐"
        style = STYLE_PROG_MARKED if es_marcado else STYLE_PROG_NORMAL
        texto = f"{cuadro}&nbsp;<font name='Courier'>{cod:>2}</font>&nbsp;{desc}"
        items.append((cod, Paragraph(texto, style), es_marcado))

    # Distribuir en 4 columnas
    n_cols = 4
    n_items = len(items)
    n_rows = (n_items + n_cols - 1) // n_cols

    grid: list[list[object]] = []
    indices_marcados: list[tuple[int, int]] = []
    for row in range(n_rows):
        fila = []
        for col in range(n_cols):
            idx = col * n_rows + row
            if idx < n_items:
                _, parag, es_marcado = items[idx]
                fila.append(parag)
                if es_marcado:
                    indices_marcados.append((row, col))
            else:
                fila.append("")
        grid.append(fila)

    col_w = 26.1 / n_cols * cm
    t = Table(grid, colWidths=[col_w] * n_cols)
    style_cmds = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("BOX", (0, 0), (-1, -1), 0.4, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.2, COLOR_BORDER),
    ]
    # Resaltar las celdas con el programa marcado
    for (r, c) in indices_marcados:
        style_cmds.append(("BACKGROUND", (c, r), (c, r), COLOR_MARK_BG))
        style_cmds.append(("BOX", (c, r), (c, r), 1.0, COLOR_MARK_BORDER))
    t.setStyle(TableStyle(style_cmds))
    return t


def _atenciones_del_dia_table(atenciones: list[Atencion]) -> Table:
    """Tabla resumen con una fila por atención del día."""
    encabezado = ["Cód", "Programa", "Modo ingreso", "IPS remite", "Encuestador", "Cargo", "Not.", "Urg.", "C.Ext."]
    filas = [encabezado]
    for a in atenciones:
        def mark(v: bool) -> str: return "✓" if v else "—"
        filas.append([
            a.cod_programa,
            a.des_programa,
            str(a.modo_ingreso or "—"),
            a.ips_remite or "—",
            a.encuestador_nombre or "—",
            a.cargo_encuestador or "—",
            mark(a.notificacion_obligatoria),
            mark(a.recuperacion_urgencias),
            mark(a.recuperacion_consulta_externa),
        ])
    col_widths = [1.2*cm, 7*cm, 2.5*cm, 4.5*cm, 4.5*cm, 3.5*cm, 1*cm, 1*cm, 1.2*cm]
    t = Table(filas, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("FONT",        (0, 0), (-1, 0),  "Helvetica-Bold", 7),
        ("FONT",        (0, 1), (-1, -1), "Helvetica", 7),
        ("BACKGROUND",  (0, 0), (-1, 0),  COLOR_PRIMARY),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  colors.white),
        ("TEXTCOLOR",   (0, 1), (-1, -1), COLOR_TEXT),
        ("BOX",         (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID",   (0, 0), (-1, -1), 0.25, COLOR_BORDER),
        ("ALIGN",       (6, 0), (-1, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    # Fondo alternado en filas de datos
    for i in range(1, len(filas)):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), COLOR_LABEL_BG))
    t.setStyle(TableStyle(style_cmds))
    return t


def _construir_pagina_multi(afiliado: AfiliadoConAtenciones) -> list:
    """Arma los flowables de UNA página con TODAS las atenciones del día."""
    atenciones = afiliado.atenciones
    primera = atenciones[0]
    elems: list = []
    sexo_full = "Femenino" if primera.sexo == "F" else "Masculino"
    codigos = [a.cod_programa for a in atenciones]

    # Cabecera — reutiliza _header_table con la primera atención
    elems.append(_header_table(afiliado, primera, 1, 1))
    elems.append(Spacer(1, 4))

    # Datos del afiliado
    elems.append(Paragraph("DATOS DEL AFILIADO", STYLE_SECTION))
    elems.append(_label_value_table([
        ("Documento",    f"{afiliado.tipo_documento} {afiliado.num_documento}"),
        ("Nombre",       afiliado.nombre_completo),
        ("Sexo",         sexo_full),
        ("Edad",         f"{primera.edad} años"),
        ("Fecha nac.",   str(primera.fecha_nacimiento)),
        ("Curso de vida", primera.curso_vida or ""),
        ("Tel 1",        primera.telefono_1 or ""),
        ("Tel 2",        primera.telefono_2 or ""),
        ("Correo",       primera.correo or ""),
        ("Régimen",      primera.regimen or ""),
        ("Dirección",    primera.direccion or ""),
        ("Depto / Mun.", f"{primera.departamento or ''} / {primera.municipio or ''}"),
    ]))

    # Atenciones del día
    elems.append(Spacer(1, 3))
    codigos_str = ", ".join(f"<font color='#16A34A'>{c}</font>" for c in codigos)
    elems.append(Paragraph(
        f"ATENCIONES DEL {primera.fecha_registro} · {len(atenciones)} programa(s): {codigos_str}",
        STYLE_SECTION,
    ))
    elems.append(_atenciones_del_dia_table(atenciones))
    elems.append(Spacer(1, 4))

    # Catálogo con todos los programas del día marcados
    elems.append(Paragraph(
        f"PROGRAMAS DE DEMANDA INDUCIDA · marcados: {codigos_str}",
        STYLE_SECTION,
    ))
    elems.append(_programas_table(codigos))

    return elems


def generar_pdf_afiliado(afiliado: AfiliadoConAtenciones, output_path: Path) -> Path:
    """Genera UN PDF de UNA página con todas las atenciones del mismo día."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(letter),
        leftMargin=10*mm, rightMargin=10*mm,
        topMargin=8*mm, bottomMargin=8*mm,
        title=f"Demanda inducida — {afiliado.pdf_key}",
        author="SIEDFASER",
    )
    elems = _construir_pagina_multi(afiliado)
    elems.append(Spacer(1, 6))
    elems.append(Paragraph(
        "Documento generado automáticamente por SIEDFASER — Sistema Inteligente de Exportación de Datos para Facturación de Seragil",
        STYLE_FOOTER,
    ))
    doc.build(elems)
    return output_path
