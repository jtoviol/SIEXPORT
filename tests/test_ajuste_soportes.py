"""Tests de Ajuste de Soportes — fusión + renombrado de PDFs de un Soporte
Unificado ya completado.

Replica, a nivel unitario, el comportamiento validado con datos reales del
script externo `unificar_soportes.py` (ver plan de la sesión): qué
identificadores son válidos/excluidos, el nombre final del PDF, y que un PDF
fuente corrupto no tumba al resto de un afiliado.

Nota: todos los documentos/nombres usados acá son ficticios (política de la
organización — nunca cédulas reales en tests ni documentación).
"""
from pathlib import Path

from reportlab.pdfgen import canvas

from efdi.services.extraction_ajuste_soportes import (
    _partir_doc_key,
    fusionar_pdfs,
    nombre_pdf_salida,
    numero_de_facturas,
    recolectar_afiliados,
)


def _pdf_valido(path: Path, texto: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path))
    c.drawString(100, 750, texto)
    c.save()


# ─── _partir_doc_key ──────────────────────────────────────────────────────────

def test_partir_doc_key_valido():
    assert _partir_doc_key("CC_1000000001") == ("CC", "1000000001")


def test_partir_doc_key_normaliza_tipo_a_mayusculas():
    assert _partir_doc_key("cc_1000000001") == ("CC", "1000000001")


def test_partir_doc_key_excluye_familia_sin_documento():
    # Patrón real: FAM_<clave_familia> — la clave trae pipes, nunca es num pura.
    assert _partir_doc_key("FAM_13|001|1|00|002|03|0001|1|100001") is None


def test_partir_doc_key_excluye_numero_alfanumerico():
    # Caso real documentado (menor sin documento propio): número NO es dígito puro.
    assert _partir_doc_key("MS_00000A000000") is None


def test_partir_doc_key_excluye_sin_guion_bajo():
    assert _partir_doc_key("CC1000000001") is None


# ─── numero_de_facturas / nombre_pdf_salida ──────────────────────────────────

def test_numero_de_facturas_extrae_sufijo():
    assert numero_de_facturas(["CAB11502", "FAB11502"]) == "11502"


def test_numero_de_facturas_none_si_no_hay_factura():
    assert numero_de_facturas(None) == ""


def test_nombre_pdf_salida_formato_exacto():
    assert nombre_pdf_salida("11502", "CC", "1000000001") == "HEV_900422757_11502_CC1000000001.pdf"


def test_nombre_pdf_salida_sanea_factura_con_caracteres_invalidos():
    # safe_filename reemplaza caracteres de filesystem inválidos por "_".
    nombre = nombre_pdf_salida("11502/2026", "TI", "2000000002")
    assert nombre == "HEV_900422757_11502_2026_TI2000000002.pdf"
    assert "/" not in nombre


# ─── fusionar_pdfs ────────────────────────────────────────────────────────────

def test_fusionar_pdfs_dos_validos(tmp_path: Path):
    p1 = tmp_path / "a.pdf"
    p2 = tmp_path / "b.pdf"
    _pdf_valido(p1, "uno")
    _pdf_valido(p2, "dos")
    destino = tmp_path / "salida" / "HEV_900422757_11502_CC1000000001.pdf"

    res = fusionar_pdfs([p1, p2], destino)

    assert res.pdfs_ok == 2
    assert res.pdfs_error == 0
    assert res.paginas == 2
    assert destino.exists()


def test_fusionar_pdfs_salta_el_corrupto_y_sigue(tmp_path: Path):
    """Un PDF fuente corrupto no tumba al resto — mismo criterio que el script
    original (`except Exception` por archivo, no por afiliado)."""
    bueno1 = tmp_path / "bueno1.pdf"
    corrupto = tmp_path / "corrupto.pdf"
    bueno2 = tmp_path / "bueno2.pdf"
    _pdf_valido(bueno1, "uno")
    corrupto.write_bytes(b"esto no es un pdf valido")
    _pdf_valido(bueno2, "dos")
    destino = tmp_path / "salida.pdf"

    res = fusionar_pdfs([bueno1, corrupto, bueno2], destino)

    assert res.pdfs_ok == 2
    assert res.pdfs_error == 1
    assert res.paginas == 2
    assert destino.exists()  # se generó igual, con las 2 páginas que sí sirvieron


def test_fusionar_pdfs_si_todos_fallan_no_escribe_nada(tmp_path: Path):
    corrupto1 = tmp_path / "corrupto1.pdf"
    corrupto2 = tmp_path / "corrupto2.pdf"
    corrupto1.write_bytes(b"basura")
    corrupto2.write_bytes(b"mas basura")
    destino = tmp_path / "salida.pdf"

    res = fusionar_pdfs([corrupto1, corrupto2], destino)

    assert res.pdfs_ok == 0
    assert res.pdfs_error == 2
    assert res.paginas == 0
    assert not destino.exists()


# ─── recolectar_afiliados ─────────────────────────────────────────────────────

def test_recolectar_afiliados_separa_validos_de_excluidos(tmp_path: Path):
    origen = tmp_path / "job_origen"
    # Afiliado válido con 2 módulos (orden alfabético de archivo = por módulo)
    _pdf_valido(origen / "lote_001" / "CC_1000000001" / "demanda_inducida_2026-05-10.pdf")
    _pdf_valido(origen / "lote_001" / "CC_1000000001" / "vacunacion.pdf")
    # Familia sin documento → excluida
    _pdf_valido(origen / "lote_001" / "FAM_claveX" / "caracterizacion_familiar.pdf")
    # Carpeta vacía (sin pdf) → se ignora, no cuenta ni como válida ni excluida
    (origen / "lote_001" / "CC_vacia").mkdir(parents=True)

    afiliados, excluidos = recolectar_afiliados(origen)

    assert len(afiliados) == 1
    assert afiliados[0].doc_key == "CC_1000000001"
    assert afiliados[0].tipo == "CC"
    assert afiliados[0].numero == "1000000001"
    # Orden alfabético por nombre de archivo: demanda_inducida antes que vacunacion.
    assert [p.name for p in afiliados[0].pdfs] == [
        "demanda_inducida_2026-05-10.pdf", "vacunacion.pdf",
    ]
    assert excluidos == ["FAM_claveX"]
