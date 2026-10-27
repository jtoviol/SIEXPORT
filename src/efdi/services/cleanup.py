"""Borrado de artefactos en disco (PDFs/ZIPs) de extracciones — manual (botón
eliminar / limpieza masiva por API) y automático (tarea programada opcional).

Toda esta lógica vivía duplicada en cada `routes_*.py` (un `shutil.rmtree`
directo por módulo, sin threadpool — bloqueaba el event loop completo
mientras borraba una carpeta grande, el mismo problema que tenía `/files`
antes de arreglarse). Queda centralizada acá, siempre detrás de
`run_in_threadpool` en el caller."""
from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta
from uuid import UUID

from efdi.config import settings
from efdi.domain.models import EstadoExtraccion
from efdi.infrastructure.job_store import store

log = logging.getLogger(__name__)

ESTADOS_TERMINALES = (
    EstadoExtraccion.COMPLETED,
    EstadoExtraccion.FAILED,
    EstadoExtraccion.CANCELLED,
)


def borrar_artefactos_extraccion(job_id: UUID) -> dict[str, int]:
    """Borra del disco: carpeta job_<id>/ y zip extraccion_<id>.zip. Idempotente.

    Síncrono — SIEMPRE debe llamarse envuelto en `run_in_threadpool` desde un
    endpoint async (puede tardar segundos/minutos con carpetas grandes en
    bind mounts de Docker Desktop)."""
    borrados = {"carpetas": 0, "zips": 0}
    job_dir = settings.data_dir / f"job_{job_id}"
    if job_dir.exists() and job_dir.is_dir():
        shutil.rmtree(job_dir, ignore_errors=True)
        borrados["carpetas"] = 1
    zip_path = settings.data_dir / f"extraccion_{job_id}.zip"
    if zip_path.exists():
        zip_path.unlink(missing_ok=True)
        borrados["zips"] = 1
    return borrados


def limpiar_extracciones(
    *, older_than_days: int | None = None, estado: str | None = None, confirmar: bool = False,
) -> dict[str, object]:
    """Limpieza masiva — borrar extracciones (de CUALQUIER módulo) por
    antigüedad o estado. Sin `confirmar=True` hace dry-run (solo reporta).

    Síncrono — llamar siempre envuelto en `run_in_threadpool`."""
    todas = store.list_all()
    candidatas = todas
    if older_than_days is not None:
        umbral = datetime.now() - timedelta(days=older_than_days)
        candidatas = [j for j in candidatas if j.creado_en < umbral]
    if estado is not None:
        candidatas = [j for j in candidatas if (j.estado.value if hasattr(j.estado, "value") else j.estado) == estado]

    resumen: dict[str, object] = {
        "modo": "ejecutado" if confirmar else "dry_run",
        "total_candidatas": len(candidatas),
        "ids": [str(j.id) for j in candidatas[:20]],
        "borradas": 0,
        "carpetas_borradas": 0,
        "zips_borrados": 0,
    }
    if confirmar:
        for j in candidatas:
            artefactos = borrar_artefactos_extraccion(j.id)
            store.delete(j.id)
            resumen["borradas"] = resumen["borradas"] + 1  # type: ignore[operator]
            resumen["carpetas_borradas"] = resumen["carpetas_borradas"] + artefactos["carpetas"]  # type: ignore[operator]
            resumen["zips_borrados"] = resumen["zips_borrados"] + artefactos["zips"]  # type: ignore[operator]
    return resumen


def ejecutar_limpieza_automatica() -> dict[str, object] | None:
    """Usada por la tarea programada (ver `main.py`). Solo borra extracciones
    en estado TERMINAL (completada/fallida/cancelada) — nunca una `pending`
    o `running`, sin importar su antigüedad. Desactivada si
    `settings.auto_cleanup_dias` es 0 o None."""
    dias = settings.auto_cleanup_dias
    if not dias or dias <= 0:
        return None

    umbral = datetime.now() - timedelta(days=dias)
    candidatas = [
        j for j in store.list_all()
        if j.creado_en < umbral and j.estado in ESTADOS_TERMINALES
    ]
    resumen: dict[str, object] = {
        "total_candidatas": len(candidatas), "borradas": 0,
        "carpetas_borradas": 0, "zips_borrados": 0,
    }
    for j in candidatas:
        try:
            artefactos = borrar_artefactos_extraccion(j.id)
            store.delete(j.id)
            resumen["borradas"] = resumen["borradas"] + 1  # type: ignore[operator]
            resumen["carpetas_borradas"] = resumen["carpetas_borradas"] + artefactos["carpetas"]  # type: ignore[operator]
            resumen["zips_borrados"] = resumen["zips_borrados"] + artefactos["zips"]  # type: ignore[operator]
        except Exception:  # noqa: BLE001
            log.exception("limpieza_automatica.job_falló", extra={"job": str(j.id)})
    log.info("limpieza_automatica.completada", extra=resumen)
    return resumen
