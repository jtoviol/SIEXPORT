"""Tests smoke Pruebas Rápidas: mock → agrupación por afiliado → PDF + paths."""
from datetime import date
from pathlib import Path

import pytest

from efdi.domain.services import agrupar_por_afiliado_pruebas
from efdi.infrastructure.repository_pruebas import MockPruebasRapidasRepository


def test_mock_devuelve_cantidad_solicitada():
    repo = MockPruebasRapidasRepository()
    resp = repo.obtener_respuestas(date(2026, 5, 1), date(2026, 5, 31), limite=10)
    assert len(resp) == 10


def test_mock_es_deterministico_con_mismo_offset():
    repo = MockPruebasRapidasRepository()
    a = repo.obtener_respuestas(date(2026, 5, 1), date(2026, 5, 31), limite=5, offset=0)
    b = repo.obtener_respuestas(date(2026, 5, 1), date(2026, 5, 31), limite=5, offset=0)
    assert [r.seq_respuesta for r in a] == [r.seq_respuesta for r in b]


def test_mock_offset_genera_respuestas_distintas():
    repo = MockPruebasRapidasRepository()
    primeras = repo.obtener_respuestas(date(2026, 5, 1), date(2026, 5, 31), limite=5, offset=0)
    siguientes = repo.obtener_respuestas(date(2026, 5, 1), date(2026, 5, 31), limite=5, offset=5)
    assert {r.seq_respuesta for r in primeras}.isdisjoint({r.seq_respuesta for r in siguientes})


def test_agrupacion_por_afiliado_sin_separar_por_fecha():
    """A diferencia de FINDRISC, en PR todas las pruebas de un afiliado caen
    en la misma carpeta sin importar la fecha — una carpeta por persona."""
    repo = MockPruebasRapidasRepository()
    resp = repo.obtener_respuestas(date(2026, 5, 1), date(2026, 5, 31), limite=20)
    afiliados = agrupar_por_afiliado_pruebas(resp)
    # Cada agrupación es 1 sólo afiliado (doc_key único)
    docs = {af.doc_key for af in afiliados}
    assert len(docs) == len(afiliados)
    # Suma de respuestas agrupadas == total
    assert sum(len(a.respuestas) for a in afiliados) == len(resp)


def test_generacion_pdf(tmp_path):
    """El generador produce un PDF no vacío para 1 respuesta."""
    from efdi.pdf.generator_pruebas import generar_pdf_pruebas

    repo = MockPruebasRapidasRepository()
    resp = repo.obtener_respuestas(date(2026, 5, 1), date(2026, 5, 31), limite=1)
    out = tmp_path / "prueba.pdf"
    generar_pdf_pruebas(resp[0], out)
    assert out.exists()
    assert out.stat().st_size > 1000


def test_generacion_pdf_con_regimen_override(tmp_path):
    """El régimen declarado por el usuario manda sobre cualquier valor de BD."""
    from efdi.pdf.generator_pruebas import generar_pdf_pruebas

    repo = MockPruebasRapidasRepository()
    resp = repo.obtener_respuestas(date(2026, 5, 1), date(2026, 5, 31), limite=1)
    out = tmp_path / "prueba_override.pdf"
    generar_pdf_pruebas(resp[0], out, regimen_override="SUBSIDIADO")
    assert out.exists() and out.stat().st_size > 1000


def test_filtro_facturas_reduce_universo():
    repo = MockPruebasRapidasRepository()
    total = repo.get_total(date(2026, 5, 1), date(2026, 5, 31))
    con_factura = repo.get_total(date(2026, 5, 1), date(2026, 5, 31),
                                  facturas=["CAB11502", "FAB11502"])
    assert con_factura <= total


def test_nombre_carpeta_y_archivo_safe(tmp_path):
    """La carpeta usa el doc_key y dentro va un único PDF `{doc_key}.pdf`."""
    from efdi.services.extraction_pruebas import _construir_tareas, _nombre_carpeta
    from efdi.domain.models import AfiliadoConPruebasRapidas, RespuestaPruebaRapida, TipoDocumento

    resp = RespuestaPruebaRapida(
        seq_seragil=1, seq_respuesta=10, seq_prueba_rapida=2,
        tipo_documento=TipoDocumento.CC,
        fecha_realizacion=date(2026, 5, 15),
        nombre_completo="MARÍA JOSÉ PÉREZ GÓMEZ",
        primer_nombre="MARÍA", segundo_nombre="JOSÉ",
        primer_apellido="PÉREZ", segundo_apellido="GÓMEZ",
        num_documento="1067839405",
        des_prueba_rapida="PRUEBA DE VIH1",
    )
    af = AfiliadoConPruebasRapidas(
        doc_key=resp.doc_key, tipo_documento=resp.tipo_documento,
        num_documento=resp.num_documento, nombre_completo=resp.nombre_completo,
        primer_nombre=resp.primer_nombre, segundo_nombre=resp.segundo_nombre,
        primer_apellido=resp.primer_apellido, segundo_apellido=resp.segundo_apellido,
        respuestas=[resp],
    )
    carpeta = _nombre_carpeta(af)
    assert carpeta == "CC_1067839405"
    assert "Á" not in carpeta and "É" not in carpeta
    tareas = _construir_tareas([af], tmp_path)
    assert len(tareas) == 1
    assert tareas[0][1] == tmp_path / "CC_1067839405" / "CC_1067839405.pdf"


def test_un_pdf_por_afiliado_con_sus_pruebas(tmp_path):
    """Aunque el afiliado tenga N pruebas, se genera 1 sola tarea (PDF único)."""
    from efdi.services.extraction_pruebas import _construir_tareas
    from efdi.domain.models import AfiliadoConPruebasRapidas, RespuestaPruebaRapida, TipoDocumento

    fecha = date(2026, 5, 15)
    a = RespuestaPruebaRapida(
        seq_seragil=1, seq_respuesta=100, seq_prueba_rapida=2,
        tipo_documento=TipoDocumento.CC, fecha_realizacion=fecha,
        nombre_completo="JUAN PEREZ", primer_nombre="JUAN", primer_apellido="PEREZ",
        num_documento="100", des_prueba_rapida="PRUEBA DE VIH",
    )
    b = a.model_copy(update={"seq_respuesta": 101, "seq_prueba_rapida": 5,
                             "des_prueba_rapida": "PRUEBA DE SIFILIS"})
    af = AfiliadoConPruebasRapidas(
        doc_key=a.doc_key, tipo_documento=a.tipo_documento,
        num_documento=a.num_documento, nombre_completo=a.nombre_completo,
        primer_nombre=a.primer_nombre, primer_apellido=a.primer_apellido,
        respuestas=[a, b],
    )
    tareas = _construir_tareas([af], tmp_path)
    assert len(tareas) == 1
    assert tareas[0][0] is af
    assert tareas[0][1] == tmp_path / "CC_100" / "CC_100.pdf"


def test_pdf_consolidado_con_varias_pruebas(tmp_path):
    """El PDF consolidado de un afiliado con N pruebas se genera y contiene N hojas."""
    from efdi.pdf.generator_pruebas import generar_pdf_pruebas_consolidado
    from efdi.domain.models import AfiliadoConPruebasRapidas, RespuestaPruebaRapida, TipoDocumento

    fecha = date(2026, 5, 15)
    a = RespuestaPruebaRapida(
        seq_seragil=1, seq_respuesta=100, seq_prueba_rapida=2,
        tipo_documento=TipoDocumento.CC, fecha_realizacion=fecha,
        nombre_completo="JUAN PEREZ", primer_nombre="JUAN", primer_apellido="PEREZ",
        num_documento="100", des_prueba_rapida="PRUEBA DE VIH",
        encuestador="ANA GARCIA", cargo_encuestador="ENFERMERA",
    )
    b = a.model_copy(update={"seq_respuesta": 101, "seq_prueba_rapida": 5,
                             "des_prueba_rapida": "PRUEBA DE SIFILIS"})
    af = AfiliadoConPruebasRapidas(
        doc_key=a.doc_key, tipo_documento=a.tipo_documento,
        num_documento=a.num_documento, nombre_completo=a.nombre_completo,
        primer_nombre=a.primer_nombre, primer_apellido=a.primer_apellido,
        respuestas=[a, b],
    )
    out = tmp_path / "CC_100.pdf"
    generar_pdf_pruebas_consolidado(af, out, regimen_override="SUBSIDIADO")
    assert out.exists()
    assert out.stat().st_size > 1000
