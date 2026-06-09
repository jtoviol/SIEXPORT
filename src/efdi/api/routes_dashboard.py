"""Endpoint cross-módulo: resumen agregado de los 3 módulos para el dashboard."""
from datetime import datetime, timedelta

from fastapi import APIRouter

from efdi.config import settings
from efdi.domain.models import EstadoExtraccion, Extraccion, ExtraccionTipo
from efdi.infrastructure.job_store import store

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# Texto humano por tipo de módulo
_MOD_LABEL = {
    ExtraccionTipo.DEMANDA_INDUCIDA:        "Demanda Inducida",
    ExtraccionTipo.FINDRISC:                "FINDRISC",
    ExtraccionTipo.GESTION_CAPTACION:       "Gestión Captación",
    ExtraccionTipo.PLANIFICACION_FAMILIAR:  "Planificación Familiar",
    ExtraccionTipo.VACUNACION:              "Vacunación",
}
# Tab id de la web por tipo de módulo (para el deep-link "ver" desde el dashboard)
_MOD_TAB = {
    ExtraccionTipo.DEMANDA_INDUCIDA:        "demanda-inducida",
    ExtraccionTipo.FINDRISC:                "findrisc",
    ExtraccionTipo.GESTION_CAPTACION:       "gestion-captacion",
    ExtraccionTipo.PLANIFICACION_FAMILIAR:  "planificacion-familiar",
    ExtraccionTipo.VACUNACION:              "vacunacion",
}


def _stats_modulo(jobs: list[Extraccion]) -> dict:
    en_curso = sum(1 for j in jobs if j.estado in (EstadoExtraccion.PENDING, EstadoExtraccion.RUNNING))
    completados = sum(1 for j in jobs if j.estado == EstadoExtraccion.COMPLETED)
    fallidos = sum(1 for j in jobs if j.estado == EstadoExtraccion.FAILED)
    ultimo = jobs[0].creado_en if jobs else None   # list_by_tipo viene ordenado DESC
    return {
        "total": len(jobs),
        "en_curso": en_curso,
        "completados": completados,
        "fallidos": fallidos,
        "ultimo": ultimo.isoformat() if ultimo else None,
    }


@router.get("/summary", summary="Resumen agregado de los 3 módulos")
async def dashboard_summary() -> dict:
    ahora = datetime.now()
    desde_24h = ahora - timedelta(hours=24)
    desde_semana = ahora - timedelta(days=7)
    desde_mes = ahora - timedelta(days=30)

    todos = store.list_all()

    # Por módulo
    modulos: dict[str, dict] = {}
    for tipo in ExtraccionTipo:
        jobs = [j for j in todos if j.tipo == tipo]
        s = _stats_modulo(jobs)
        s["label"] = _MOD_LABEL[tipo]
        s["tab"] = _MOD_TAB[tipo]
        modulos[tipo.value] = s

    # Métricas globales
    pdfs_hoy = sum(j.total_pdfs for j in todos if j.creado_en >= desde_24h)
    pdfs_semana = sum(j.total_pdfs for j in todos if j.creado_en >= desde_semana)
    pdfs_mes = sum(j.total_pdfs for j in todos if j.creado_en >= desde_mes)
    afiliados_mes = sum(j.total_afiliados for j in todos if j.creado_en >= desde_mes)

    en_curso = sum(
        1 for j in todos
        if j.estado in (EstadoExtraccion.PENDING, EstadoExtraccion.RUNNING)
    )
    fallidas_24h = sum(
        1 for j in todos
        if j.estado == EstadoExtraccion.FAILED and j.creado_en >= desde_24h
    )

    # Últimas 8 extracciones de cualquier módulo (ya viene DESC)
    recientes = []
    for j in todos[:8]:
        recientes.append({
            "id": str(j.id),
            "tipo": j.tipo.value if hasattr(j.tipo, "value") else j.tipo,
            "tipo_label": _MOD_LABEL.get(
                ExtraccionTipo(j.tipo) if not isinstance(j.tipo, ExtraccionTipo) else j.tipo,
                "—",
            ),
            "tab": _MOD_TAB.get(
                ExtraccionTipo(j.tipo) if not isinstance(j.tipo, ExtraccionTipo) else j.tipo,
                "demanda-inducida",
            ),
            "nombre": j.nombre,
            "estado": j.estado.value if hasattr(j.estado, "value") else j.estado,
            "creado_en": j.creado_en.isoformat(),
            "total_pdfs": j.total_pdfs,
            "total_afiliados": j.total_afiliados,
            "desde": j.desde.isoformat() if j.desde else None,
            "hasta": j.hasta.isoformat() if j.hasta else None,
        })

    return {
        "now": ahora.isoformat(),
        "modo_datos": "mock" if settings.use_mock else "sql_server",
        "global": {
            "en_curso": en_curso,
            "fallidas_24h": fallidas_24h,
            "pdfs_hoy": pdfs_hoy,
            "pdfs_semana": pdfs_semana,
            "pdfs_mes": pdfs_mes,
            "afiliados_mes": afiliados_mes,
        },
        "modulos": modulos,
        "recientes": recientes,
    }
