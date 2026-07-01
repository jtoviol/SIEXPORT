"""Tests smoke Planificación Familiar: mock → agrupación → PDF."""
from datetime import date

import pytest

from efdi.domain.services import agrupar_por_afiliado_planfami
from efdi.infrastructure.repository_planfami import MockPlanFamiRepository


def test_mock_cantidad():
    repo = MockPlanFamiRepository()
    regs = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=15)
    assert len(regs) == 15


def test_mock_determinismo():
    repo = MockPlanFamiRepository()
    a = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=5, offset=0)
    b = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=5, offset=0)
    assert [r.num_documento for r in a] == [r.num_documento for r in b]


def test_agrupacion_por_documento_y_fecha_gestion():
    """agrupar_por_afiliado_planfami → 1 PDF por (doc, fecha_gestion)."""
    repo = MockPlanFamiRepository()
    regs = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=20)
    afiliados = agrupar_por_afiliado_planfami(regs)
    for af in afiliados:
        keys = {(r.doc_key, r.fecha_gestion) for r in af.registros}
        assert len(keys) == 1
    assert sum(len(a.registros) for a in afiliados) == len(regs)


def test_generacion_pdf(tmp_path):
    """El generador PlanFami produce un PDF razonable."""
    from efdi.pdf.generator_planfami import generar_pdf_planfami

    repo = MockPlanFamiRepository()
    regs = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=3)
    afiliados = agrupar_por_afiliado_planfami(regs)
    out = tmp_path / "planfami.pdf"
    generar_pdf_planfami(afiliados[0], out)
    assert out.exists()
    assert out.stat().st_size > 1000


def test_pdf_con_regimen_override(tmp_path):
    """Si viene regimen_override (del filtro CAB/FAB), se imprime el del job, no el de la BD."""
    from efdi.pdf.generator_planfami import generar_pdf_planfami

    repo = MockPlanFamiRepository()
    regs = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=3)
    afiliados = agrupar_por_afiliado_planfami(regs)
    out = tmp_path / "planfami_override.pdf"
    # No raise → contrato del API se respeta
    generar_pdf_planfami(afiliados[0], out, regimen_override="SUBSIDIADO")
    assert out.exists()
