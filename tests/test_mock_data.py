"""Tests del generador determinista."""
from datetime import date

from efdi.infrastructure.mock_data import generar_atenciones


def test_genera_cantidad_correcta() -> None:
    atenciones = generar_atenciones(limite=25, desde=date(2026, 1, 1), hasta=date(2026, 5, 1))
    assert 1 <= len(atenciones) <= 25


def test_determinista_con_mismo_seed() -> None:
    a1 = generar_atenciones(limite=10, desde=date(2026, 1, 1), hasta=date(2026, 5, 1), seed=42)
    a2 = generar_atenciones(limite=10, desde=date(2026, 1, 1), hasta=date(2026, 5, 1), seed=42)
    assert [a.seq_seragil for a in a1] == [a.seq_seragil for a in a2]
    assert [a.num_documento for a in a1] == [a.num_documento for a in a2]


def test_fechas_dentro_del_rango() -> None:
    desde, hasta = date(2026, 1, 1), date(2026, 3, 1)
    atenciones = generar_atenciones(limite=20, desde=desde, hasta=hasta)
    for a in atenciones:
        assert desde <= a.fecha_registro <= hasta


def test_un_afiliado_tiene_varias_atenciones() -> None:
    atenciones = generar_atenciones(limite=25, desde=date(2026, 1, 1), hasta=date(2026, 5, 1))
    docs = [a.doc_key for a in atenciones]
    assert len(set(docs)) < len(docs), "Debería haber al menos un afiliado con >1 atención"


def test_offset_genera_registros_distintos() -> None:
    desde, hasta = date(2026, 1, 1), date(2026, 5, 1)
    lote1 = generar_atenciones(limite=10, desde=desde, hasta=hasta, offset=0)
    lote2 = generar_atenciones(limite=10, desde=desde, hasta=hasta, offset=10)
    docs_l1 = {a.doc_key for a in lote1}
    docs_l2 = {a.doc_key for a in lote2}
    # Los offsets distintos deben dar afiliados mayormente distintos
    overlap = docs_l1 & docs_l2
    assert len(overlap) < len(docs_l1), "Offset distinto debería dar registros distintos"
