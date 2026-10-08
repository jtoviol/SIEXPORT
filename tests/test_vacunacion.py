"""Tests smoke Vacunación: mock SQL (régimen + fecha, sin Excel) → agrupación → PDF."""
from datetime import date

from efdi.domain.services import agrupar_por_afiliado_vacunacion
from efdi.infrastructure.repository_vacunacion import MockVacunacionRepository


def test_mock_devuelve_cantidad_solicitada():
    repo = MockVacunacionRepository()
    regs = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=10)
    assert len(regs) == 10


def test_mock_es_deterministico_con_mismo_offset():
    repo = MockVacunacionRepository()
    a = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=5, offset=0)
    b = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=5, offset=0)
    assert [r.num_documento for r in a] == [r.num_documento for r in b]


def test_mock_filtra_por_regimen():
    """Con régimen, todos los registros devueltos deben ser de ese régimen."""
    repo = MockVacunacionRepository()
    regs = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=50, regimen="SUBSIDIADO")
    assert regs
    assert all(r.regimen == "SUBSIDIADO" for r in regs)


def test_get_total_con_regimen_es_menor_o_igual_al_total():
    repo = MockVacunacionRepository()
    total = repo.get_total(date(2026, 5, 1), date(2026, 5, 31))
    con_regimen = repo.get_total(date(2026, 5, 1), date(2026, 5, 31), regimen="CONTRIBUTIVO")
    assert con_regimen <= total


def test_agrupacion_por_documento_sin_fecha():
    """agrupar_por_afiliado_vacunacion colapsa por doc_key (1 carné por persona)."""
    repo = MockVacunacionRepository()
    regs = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=20)
    afiliados = agrupar_por_afiliado_vacunacion(regs)
    docs = {a.doc_key for a in afiliados}
    assert len(docs) == len(afiliados)
    assert sum(len(a.vacunas) for a in afiliados) == len(regs)


def test_generacion_pdf(tmp_path):
    from efdi.pdf.generator_vacunacion import generar_pdf_vacunacion

    repo = MockVacunacionRepository()
    regs = repo.obtener_registros(date(2026, 5, 1), date(2026, 5, 31), limite=3)
    afiliados = agrupar_por_afiliado_vacunacion(regs)
    out = tmp_path / "vacunacion.pdf"
    generar_pdf_vacunacion(afiliados[0], out)
    assert out.exists()
    assert out.stat().st_size > 1000
