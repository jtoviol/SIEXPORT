"""Tests del módulo Caracterización Familiar."""
from datetime import date

from efdi.domain.models import RegistroCaracterizacion
from efdi.domain.services import agrupar_por_familia_caracterizacion
from efdi.infrastructure.repository_caracterizacion import MockCaracterizacionRepository


def _reg(**overrides) -> RegistroCaracterizacion:
    base = dict(
        departamento="13", municipio="001", area="1", corregimiento="00",
        barrio_vereda="002", manzana="03", vivienda="0001", familia="1",
        ciuf="100001", tipo_documento="CC", num_documento="123",
        nombres_apellidos="JUAN PEREZ", parentesco="CABEZA DE FAMILIA",
    )
    base.update(overrides)
    return RegistroCaracterizacion(**base)


def test_familia_key_es_jerarquia_completa():
    r = _reg()
    assert r.familia_key == "13|001|1|00|002|03|0001|1|100001"


def test_familia_key_campos_vacios_no_colapsan():
    # Dos familias que solo difieren en un nivel vacío vs '0' no deben mezclarse
    a = _reg(manzana=None)
    b = _reg(manzana="03")
    assert a.familia_key != b.familia_key


def test_agrupar_misma_familia_un_grupo():
    regs = [
        _reg(num_documento="111", parentesco="CABEZA DE FAMILIA"),
        _reg(num_documento="222", parentesco="HIJO(A)"),
        _reg(num_documento="333", parentesco="CONYUGE"),
    ]
    familias = agrupar_por_familia_caracterizacion(regs)
    assert len(familias) == 1
    assert familias[0].total_integrantes == 3
    # Mantiene el orden en que llegaron de la query
    assert [r.num_documento for r in familias[0].registros] == ["111", "222", "333"]


def test_agrupar_familias_distintas_por_ciuf():
    regs = [_reg(ciuf="100001"), _reg(ciuf="100002")]
    familias = agrupar_por_familia_caracterizacion(regs)
    assert len(familias) == 2


def test_mock_agrupa_4_integrantes_por_familia():
    # limite/offset en FAMILIAS: 10 familias → 40 registros-persona
    repo = MockCaracterizacionRepository()
    regs = repo.obtener_registros(date(2026, 6, 1), date(2026, 6, 11), limite=10)
    familias = agrupar_por_familia_caracterizacion(regs)
    assert len(regs) == 40
    assert len(familias) == 10
    assert all(f.total_integrantes == 4 for f in familias)


def test_mock_offset_consistente():
    # La misma familia global produce los mismos registros sin importar el lote
    repo = MockCaracterizacionRepository()
    todo = repo.obtener_registros(date(2026, 6, 1), date(2026, 6, 11), limite=10, offset=0)
    lote2 = repo.obtener_registros(date(2026, 6, 1), date(2026, 6, 11), limite=5, offset=5)
    # familia #5 arranca en la fila 20 del fetch completo (4 integrantes/familia)
    assert todo[20].num_documento == lote2[0].num_documento
    assert todo[20].familia_key == lote2[0].familia_key


def test_lotes_no_parten_familias():
    # Ningún familia_key puede aparecer en dos lotes distintos
    repo = MockCaracterizacionRepository()
    lote1 = repo.obtener_registros(date(2026, 6, 1), date(2026, 6, 11), limite=5, offset=0)
    lote2 = repo.obtener_registros(date(2026, 6, 1), date(2026, 6, 11), limite=5, offset=5)
    keys1 = {r.familia_key for r in lote1}
    keys2 = {r.familia_key for r in lote2}
    assert keys1.isdisjoint(keys2)
    assert len(keys1) == 5 and len(keys2) == 5


def test_generar_pdf_familia(tmp_path):
    from efdi.pdf.generator_caracterizacion import generar_pdf_caracterizacion

    repo = MockCaracterizacionRepository()
    regs = repo.obtener_registros(date(2026, 6, 1), date(2026, 6, 11), limite=4)
    familia = agrupar_por_familia_caracterizacion(regs)[0]
    out = tmp_path / f"{familia.pdf_key}.pdf"
    generar_pdf_caracterizacion(familia, out)
    assert out.exists()
    assert out.stat().st_size > 1000
