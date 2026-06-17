"""Lógica de dominio — agrupación de atenciones/registros por afiliado."""
from collections import defaultdict

from efdi.domain.models import (
    AfiliadoConAtenciones,
    AfiliadoConCaptacion,
    AfiliadoConFindrisc,
    AfiliadoConPlanFamiliar,
    AfiliadoConPruebasRapidas,
    AfiliadoConVacunas,
    Atencion,
    FamiliaCaracterizada,
    RegistroCaptacion,
    RegistroCaracterizacion,
    RegistroFindrisc,
    RegistroPlanFamiliar,
    RegistroVacuna,
    RespuestaPruebaRapida,
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


def agrupar_por_afiliado_vacunacion(
    registros: list[RegistroVacuna],
) -> list[AfiliadoConVacunas]:
    """Agrupa registros de Vacunación por afiliado (sin fecha) — 1 carné por persona.

    A diferencia de los otros módulos, NO se separa por fecha. El carné contiene
    TODAS las vacunas del afiliado tal cual vienen en el Excel.
    """
    grupos: dict[str, list[RegistroVacuna]] = defaultdict(list)
    for r in registros:
        grupos[r.doc_key].append(r)

    resultado: list[AfiliadoConVacunas] = []
    for _, grupo in grupos.items():
        primero = grupo[0]
        nombre = " ".join(
            p for p in [
                primero.primer_nombre,
                primero.segundo_nombre,
                primero.primer_apellido,
                primero.segundo_apellido,
            ] if p
        )
        resultado.append(
            AfiliadoConVacunas(
                doc_key=primero.doc_key,
                tipo_documento=primero.tipo_documento,
                num_documento=primero.num_documento,
                nombre_completo=nombre,
                sexo=primero.sexo,
                edad=primero.edad,
                fecha_nacimiento=primero.fecha_nacimiento,
                tipo_identificacion_desc=primero.tipo_identificacion_desc,
                direccion=primero.direccion,
                telefono_1=primero.telefono_1,
                telefono_2=primero.telefono_2,
                correo=primero.correo,
                departamento=primero.departamento,
                municipio=primero.municipio,
                regimen=primero.regimen,
                vacunas=grupo,
            )
        )
    return sorted(resultado, key=lambda x: x.doc_key)


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


def agrupar_por_afiliado_pruebas(
    respuestas: list[RespuestaPruebaRapida],
) -> list[AfiliadoConPruebasRapidas]:
    """Agrupa respuestas de Pruebas Rápidas por afiliado (doc_key).

    1 carpeta = 1 afiliado. Si la persona se hizo N pruebas (en una o varias
    fechas) → todas caen en la misma carpeta del ZIP. El PDF individual
    representa cada prueba por separado.
    """
    grupos: dict[str, list[RespuestaPruebaRapida]] = defaultdict(list)
    for r in respuestas:
        grupos[r.doc_key].append(r)

    resultado: list[AfiliadoConPruebasRapidas] = []
    for _, grupo in grupos.items():
        primero = grupo[0]
        # Ordenar respuestas por fecha realización + seq para reproducibilidad
        grupo.sort(key=lambda x: (x.fecha_realizacion, x.seq_respuesta))
        resultado.append(
            AfiliadoConPruebasRapidas(
                doc_key=primero.doc_key,
                tipo_documento=primero.tipo_documento,
                num_documento=primero.num_documento,
                nombre_completo=primero.nombre_completo,
                primer_nombre=primero.primer_nombre,
                segundo_nombre=primero.segundo_nombre,
                primer_apellido=primero.primer_apellido,
                segundo_apellido=primero.segundo_apellido,
                respuestas=grupo,
            )
        )
    return sorted(resultado, key=lambda x: x.doc_key)


def agrupar_por_familia_caracterizacion(
    registros: list[RegistroCaracterizacion],
) -> list[FamiliaCaracterizada]:
    """Agrupa registros de Caracterización Familiar por familia.

    La llave es la jerarquía geográfica completa + vivienda + familia + ciuf
    (RegistroCaracterizacion.familia_key). 1 PDF por familia con todos sus
    integrantes, en el orden en que la query los devolvió.
    """
    grupos: dict[str, list[RegistroCaracterizacion]] = defaultdict(list)
    for r in registros:
        grupos[r.familia_key].append(r)

    resultado: list[FamiliaCaracterizada] = []
    for clave, grupo in grupos.items():
        resultado.append(FamiliaCaracterizada(familia_key=clave, registros=grupo))
    return sorted(resultado, key=lambda x: x.familia_key)
