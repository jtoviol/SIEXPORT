"""Lógica de dominio — agrupación de atenciones/registros por afiliado."""
from collections import defaultdict

from efdi.domain.models import (
    AfiliadoConAtenciones,
    AfiliadoConCaptacion,
    AfiliadoConFindrisc,
    AfiliadoConPlanFamiliar,
    Atencion,
    RegistroCaptacion,
    RegistroFindrisc,
    RegistroPlanFamiliar,
)


def agrupar_por_afiliado(atenciones: list[Atencion]) -> list[AfiliadoConAtenciones]:
    """Agrupa atenciones por (documento, fecha_registro) — 1 PDF por afiliado por día."""
    grupos: dict[str, list[Atencion]] = defaultdict(list)
    for a in atenciones:
        clave = f"{a.doc_key}_{a.fecha_registro}"
        grupos[clave].append(a)

    resultado: list[AfiliadoConAtenciones] = []
    for _, grupo in grupos.items():
        primera = grupo[0]
        nombre = " ".join(
            p for p in [
                primera.primer_nombre,
                primera.segundo_nombre,
                primera.primer_apellido,
                primera.segundo_apellido,
            ] if p
        )
        resultado.append(
            AfiliadoConAtenciones(
                doc_key=primera.doc_key,
                tipo_documento=primera.tipo_documento,
                num_documento=primera.num_documento,
                nombre_completo=nombre,
                fecha_registro=primera.fecha_registro,
                atenciones=grupo,
            )
        )
    return sorted(resultado, key=lambda x: (x.doc_key, x.fecha_registro))


def agrupar_por_afiliado_findrisc(registros: list[RegistroFindrisc]) -> list[AfiliadoConFindrisc]:
    """Agrupa registros FINDRISC por (documento, fecha_registro) — 1 PDF por afiliado por día."""
    grupos: dict[str, list[RegistroFindrisc]] = defaultdict(list)
    for r in registros:
        clave = f"{r.doc_key}_{r.fecha_registro}"
        grupos[clave].append(r)

    resultado: list[AfiliadoConFindrisc] = []
    for _, grupo in grupos.items():
        primero = grupo[0]
        resultado.append(
            AfiliadoConFindrisc(
                doc_key=primero.doc_key,
                tipo_documento=primero.tipo_documento,
                num_documento=primero.num_documento,
                nombre_completo=primero.nombre_completo,
                fecha_registro=primero.fecha_registro,
                registros=grupo,
            )
        )
    return sorted(resultado, key=lambda x: (x.doc_key, x.fecha_registro))


def agrupar_por_afiliado_captacion(registros: list[RegistroCaptacion]) -> list[AfiliadoConCaptacion]:
    """Agrupa registros de Captación por (documento, fecha_captacion) — 1 PDF por afiliado por fecha.

    Si una persona tiene N filas con la misma fecha_captacion → caen en el mismo PDF.
    Si tiene fechas distintas → un PDF por cada fecha.
    """
    grupos: dict[str, list[RegistroCaptacion]] = defaultdict(list)
    for r in registros:
        clave = f"{r.doc_key}_{r.fecha_captacion}"
        grupos[clave].append(r)

    resultado: list[AfiliadoConCaptacion] = []
    for _, grupo in grupos.items():
        primero = grupo[0]
        resultado.append(
            AfiliadoConCaptacion(
                doc_key=primero.doc_key,
                tipo_documento=primero.tipo_documento,
                num_documento=primero.num_documento,
                nombre_completo=primero.nombre_completo,
                fecha_captacion=primero.fecha_captacion,
                registros=grupo,
            )
        )
    return sorted(resultado, key=lambda x: (x.doc_key, x.fecha_captacion))


def agrupar_por_afiliado_planfami(
    registros: list[RegistroPlanFamiliar],
) -> list[AfiliadoConPlanFamiliar]:
    """Agrupa registros de Planificación Familiar por (documento, fecha_gestion).

    Si una persona tiene N filas con la misma fec_gestion_seguimiento → caen en el
    mismo PDF. Si tiene fechas distintas → un PDF por cada fecha.
    """
    grupos: dict[str, list[RegistroPlanFamiliar]] = defaultdict(list)
    for r in registros:
        clave = f"{r.doc_key}_{r.fecha_gestion}"
        grupos[clave].append(r)

    resultado: list[AfiliadoConPlanFamiliar] = []
    for _, grupo in grupos.items():
        primero = grupo[0]
        resultado.append(
            AfiliadoConPlanFamiliar(
                doc_key=primero.doc_key,
                tipo_documento=primero.tipo_documento,
                num_documento=primero.num_documento,
                nombre_completo=primero.nombre_completo,
                fecha_gestion=primero.fecha_gestion,
                registros=grupo,
            )
        )
    return sorted(resultado, key=lambda x: (x.doc_key, x.fecha_gestion))
