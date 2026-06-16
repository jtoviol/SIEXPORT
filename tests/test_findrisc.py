"""Tests smoke FINDRISC: mock → agrupación → PDF."""
from datetime import date
from pathlib import Path

import pytest

from efdi.domain.services import agrupar_por_afiliado_findrisc
from efdi.infrastructure.repository_findrisc import MockFindriscRepository


def test_mock_devuelve_cantidad_solicitada():
    repo = MockFindriscRepository()
    regs = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=10)
    assert len(regs) == 10


def test_mock_es_deterministico_con_mismo_offset():
    """Mismo seed → mismo registro (clave para paginación reproducible)."""
    repo = MockFindriscRepository()
    a = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=5, offset=0)
    b = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=5, offset=0)
    assert [r.num_documento for r in a] == [r.num_documento for r in b]


def test_mock_offset_genera_registros_distintos():
    repo = MockFindriscRepository()
    primeros = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=5, offset=0)
    siguientes = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=5, offset=5)
    assert {r.num_documento for r in primeros}.isdisjoint({r.num_documento for r in siguientes})


def test_agrupacion_por_documento_y_fecha():
    """agrupar_por_afiliado_findrisc colapsa por (doc, fecha_registro)."""
    repo = MockFindriscRepository()
    regs = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=20)
    afiliados = agrupar_por_afiliado_findrisc(regs)
    # Cada agrupación es 1 doc + 1 fecha
    for af in afiliados:
        keys = {(r.doc_key, r.fecha_registro) for r in af.registros}
        assert len(keys) == 1
    # Suma de registros agrupados == total
    assert sum(len(a.registros) for a in afiliados) == len(regs)


def test_generacion_pdf(tmp_path):
    """El generador FINDRISC produce un PDF no vacío."""
    from efdi.pdf.generator_findrisc import generar_pdf_findrisc

    repo = MockFindriscRepository()
    regs = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=3)
    afiliados = agrupar_por_afiliado_findrisc(regs)
    out = tmp_path / "findrisc.pdf"
    generar_pdf_findrisc(afiliados[0], out)
    assert out.exists()
    assert out.stat().st_size > 1000   # PDF razonable, no es solo header


def test_filtro_facturas_reduce_universo():
    """Con facturas mockeadas, el repo devuelve subset filtrado."""
    repo = MockFindriscRepository()
    total = repo.get_total(date(2026, 5, 1), date(2026, 5, 31))
    con_factura = repo.get_total(date(2026, 5, 1), date(2026, 5, 31),
                                  facturas=["CAB11502", "FAB11502"])
    assert con_factura <= total      # No puede traer más
