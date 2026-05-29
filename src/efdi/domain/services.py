"""Lógica de dominio — agrupación de atenciones por afiliado."""
from collections import defaultdict

from efdi.domain.models import AfiliadoConAtenciones, Atencion


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
