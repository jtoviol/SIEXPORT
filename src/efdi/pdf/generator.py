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


def _programas_table(cod_marcado: str) -> Table:
    """Tabla de 4 columnas con los 124 programas del catálogo.

    Marca con ☒ + fondo verde el que coincide con cod_marcado.
    """
    catalogo = cargar_catalogo()
    if not catalogo:
        return Table([["Catálogo de programas no disponible"]])

    items = []
    for cod, desc in catalogo:
        es_marcado = cod == cod_marcado
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


def _construir_pagina(afiliado: AfiliadoConAtenciones, atencion: Atencion,
                     page_n: int, page_total: int) -> list:
    """Arma los flowables de UNA página (correspondiente a una atención)."""
    elems: list = []
    sexo_full = "Femenino" if afiliado.atenciones[0].sexo == "F" else "Masculino"

    # Cabecera con logo
    elems.append(_header_table(afiliado, atencion, page_n, page_total))
    elems.append(Spacer(1, 4))

    # Datos del afiliado (compacto, una sola línea con 4 columnas)
    elems.append(Paragraph("DATOS DEL AFILIADO", STYLE_SECTION))
    nac = atencion.fecha_nacimiento
    elems.append(_label_value_table([
        ("Documento", f"{afiliado.tipo_documento} {afiliado.num_documento}"),
        ("Nombre", afiliado.nombre_completo),
        ("Sexo", sexo_full),
        ("Edad", f"{atencion.edad} años"),
        ("Fecha nac.", str(nac)),
        ("Curso de vida", atencion.curso_vida or ""),
        ("Tel 1", atencion.telefono_1 or ""),
        ("Tel 2", atencion.telefono_2 or ""),
        ("Correo", atencion.correo or ""),
        ("Régimen", atencion.regimen or ""),
        ("Dirección", atencion.direccion or ""),
        ("Depto / Mun.", f"{atencion.departamento or ''} / {atencion.municipio or ''}"),
    ]))

    # Detalle de la atención
    elems.append(Spacer(1, 3))
    elems.append(Paragraph("DETALLE DE LA ATENCIÓN", STYLE_SECTION))
    modo_label = str(atencion.modo_ingreso or "—")
    elems.append(_label_value_table([
        ("Fecha registro", str(atencion.fecha_registro)),
        ("Fecha ejecución", str(atencion.fecha_atencion) if atencion.fecha_atencion else "—"),
        ("Cód programa", atencion.cod_programa),
        ("Modo ingreso", modo_label),
        ("Programa", atencion.des_programa),
        ("", ""),
        ("IPS remite", atencion.ips_remite or ""),
        ("IPS atiende", atencion.ips_atiende or ""),
        ("Encuestador", atencion.encuestador_nombre or ""),
        ("Cargo", atencion.cargo_encuestador or ""),
        ("Tipo remitente", atencion.des_remitente or ""),
        ("RIAS grupo riesgo", atencion.rias_grupo_riesgo or ""),
    ]))
    elems.append(Spacer(1, 3))
    elems.append(_flags_table(atencion))
    elems.append(Spacer(1, 4))

    # Catálogo de programas con la X marcada
    elems.append(Paragraph(
        f"PROGRAMAS DE DEMANDA INDUCIDA · marcado: <font color='#16A34A'>{atencion.cod_programa}</font>",
        STYLE_SECTION,
    ))
    elems.append(_programas_table(atencion.cod_programa))

    return elems


def generar_pdf_afiliado(afiliado: AfiliadoConAtenciones, output_path: Path) -> Path:
    """Genera UN solo PDF con N páginas (una por atención del afiliado).

    Cada página marca el programa correspondiente y lista el resto en ☐.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(letter),  # ANCHO (apaisado, 11"x8.5")
        leftMargin=10*mm, rightMargin=10*mm,
        topMargin=8*mm, bottomMargin=8*mm,
        title=f"Demanda inducida — {afiliado.doc_key}",
        author="DataDownload",
    )
    elems: list = []
    total = afiliado.total_atenciones

    for i, atencion in enumerate(afiliado.atenciones, start=1):
        elems.extend(_construir_pagina(afiliado, atencion, i, total))
        if i < total:
            elems.append(PageBreak())

    # Footer global solo al final de la última página
    elems.append(Spacer(1, 6))
    elems.append(Paragraph(
        "Documento generado automáticamente por DataDownload — Sistema de exportación",
        STYLE_FOOTER,
    ))

    doc.build(elems)
    return output_path


# Compatibilidad: la función vieja sigue existiendo pero ahora redirige al modo nuevo
def generar_pdf_atencion(atencion: Atencion, output_path: Path) -> Path:
    """Genera un PDF de UNA atención (1 página). Mantenido por compatibilidad."""
    # Construir un afiliado virtual con esta sola atención
    nombre = " ".join(p for p in [
        atencion.primer_nombre, atencion.segundo_nombre,
        atencion.primer_apellido, atencion.segundo_apellido,
    ] if p)
    afiliado_virtual = AfiliadoConAtenciones(
        doc_key=atencion.doc_key,
        tipo_documento=atencion.tipo_documento,
        num_documento=atencion.num_documento,
        nombre_completo=nombre,
        atenciones=[atencion],
    )
    return generar_pdf_afiliado(afiliado_virtual, output_path)
