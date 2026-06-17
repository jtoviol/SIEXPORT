"""Orquestador Pruebas Rápidas: divide en lotes → query → agrupar por afiliado →
PDFs (1 por prueba, todos en la carpeta del afiliado) → zip.

Estructura del ZIP (a diferencia de los otros módulos):
    lote_001/
      CC_1067839405_PEREZ_GOMEZ_JUAN_CARLOS/      ← una carpeta por afiliado
        CC_1067839405_PRUEBA_DE_VIH1_2026-05-15.pdf
        CC_1067839405_PRUEBA_DE_SIFILIS_2026-05-15.pdf
      CC_1144567321_GOMEZ_RUIZ_MARIA/
        CC_1144567321_PRUEBA_DE_EMBARAZO_2026-05-18.pdf
"""
import logging
import math
import multiprocessing as mp
import os
import re
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from efdi.config import settings
from efdi.domain.models import (
    AfiliadoConPruebasRapidas,
    EstadoExtraccion,
    Extraccion,
    Lote,
    RespuestaPruebaRapida,
)
from efdi.domain.services import agrupar_por_afiliado_pruebas
from efdi.infrastructure.job_store import store
from efdi.infrastructure.repository_pruebas import get_pruebas_repository
from efdi.pdf.generator_pruebas import generar_pdf_pruebas
from efdi.pdf.parallel_pruebas import _worker as pdf_worker_pruebas

log = logging.getLogger(__name__)


_INVALID_FS_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')
_MULTI_UNDERSCORE = re.compile(r"_+")
_NON_ASCII = re.compile(r"[^A-Z0-9_-]")


def _safe_part(s: str | None) -> str:
    """Sanitiza un fragmento para ser parte segura de un nombre de archivo/carpeta.

    Mayúsculas, ASCII, sin espacios. Vacío si no hay nada útil.
    """
    if not s:
        return ""
    import unicodedata
    txt = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    txt = txt.upper().strip()
    txt = _INVALID_FS_CHARS.sub("_", txt)
    txt = txt.replace(" ", "_")
    txt = _NON_ASCII.sub("_", txt)
    txt = _MULTI_UNDERSCORE.sub("_", txt).strip("._-")
    return txt[:60]


def _nombre_carpeta(af: AfiliadoConPruebasRapidas) -> str:
    """`{doc_key}_{APELLIDOS_NOMBRES}` truncado y safe-filename."""
    partes = [af.primer_apellido, af.segundo_apellido, af.primer_nombre, af.segundo_nombre]
    nombres = "_".join(_safe_part(p) for p in partes if p)
    if not nombres:
        nombres = _safe_part(af.nombre_completo)
    base = af.doc_key
    if nombres:
        base = f"{base}_{nombres}"
    return _MULTI_UNDERSCORE.sub("_", base).strip("._-")[:100]


def _nombre_archivo(reg: RespuestaPruebaRapida) -> str:
    """`{doc_key}_{NOMBRE_PRUEBA}_{fecha}` (sin extensión)."""
    prueba = _safe_part(reg.des_prueba_rapida) or "PRUEBA"
    base = f"{reg.doc_key}_{prueba}_{reg.fecha_realizacion.isoformat()}"
    return _MULTI_UNDERSCORE.sub("_", base).strip("._-")[:120]


def _construir_tareas(
    afiliados: list[AfiliadoConPruebasRapidas], lote_dir: Path,
) -> list[tuple[RespuestaPruebaRapida, Path]]:
    """1 tarea por respuesta. Si dos pruebas del MISMO afiliado generan el mismo
    nombre de archivo (misma prueba misma fecha — VIH1 y VIH2 comparten nombre
    cuando el catálogo tiene aliases) → desambigua con `_seq{seq_respuesta}`.
    """
    tareas: list[tuple[RespuestaPruebaRapida, Path]] = []
    for af in afiliados:
        carpeta = lote_dir / _nombre_carpeta(af)
        vistos: set[str] = set()
        for resp in af.respuestas:
            nombre = _nombre_archivo(resp)
            if nombre in vistos:
                nombre = f"{nombre}_seq{resp.seq_respuesta}"
            vistos.add(nombre)
            tareas.append((resp, carpeta / f"{nombre}.pdf"))
    return tareas


def _generar_pdfs_pruebas(
    tareas: list[tuple[RespuestaPruebaRapida, Path]],
    pool: "mp.pool.Pool | None" = None,
    regimen_override: str | None = None,
) -> int:
    n = len(tareas)
    if settings.pdf_workers == 0 or n < settings.pdf_parallel_threshold or pool is None:
        for reg, path in tareas:
            path.parent.mkdir(parents=True, exist_ok=True)
            generar_pdf_pruebas(reg, path, regimen_override=regimen_override)
        return n
    dirs = {p.parent for _, p in tareas}
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    payload = [(reg, str(p), regimen_override) for reg, p in tareas]
    chunksize = max(20, n // (pool._processes * 8))  # type: ignore[attr-defined]
    results = list(pool.imap_unordered(pdf_worker_pruebas, payload, chunksize=chunksize))
    return len(results)


def _procesar_lote_pruebas(job: Extraccion, lote: Lote, pool: "mp.pool.Pool | None" = None) -> Lote:
    log.info("pruebas.lote.start", extra={"job": str(job.id), "lote": lote.numero})
    lote.estado = EstadoExtraccion.RUNNING
    lote.iniciado_en = datetime.now()
    store.save_lote(lote)

    try:
        lote.fase = "Consultando base de datos…"
        store.save_lote(lote)
        repo = get_pruebas_repository()
        respuestas = repo.obtener_respuestas(
            desde=job.desde,
            hasta=job.hasta,
            limite=lote.tamano,
            offset=lote.offset_inicio,
            facturas=job.facturas,
        )
        lote.total_atenciones = len(respuestas)

        if not respuestas:
            lote.fase = ""
            lote.estado = EstadoExtraccion.COMPLETED
            lote.completado_en = datetime.now()
            store.save_lote(lote)
            return lote

        afiliados = agrupar_por_afiliado_pruebas(respuestas)
        lote.total_afiliados = len(afiliados)

        lote.fase = f"Generando PDFs ({len(respuestas)} pruebas, {len(afiliados)} afiliados)…"
        store.save_lote(lote)

        lote_dir = settings.data_dir / f"job_{job.id}" / f"lote_{lote.numero:03d}"
        lote_dir.mkdir(parents=True, exist_ok=True)

        tareas = _construir_tareas(afiliados, lote_dir)
        total_pdfs = _generar_pdfs_pruebas(tareas, pool=pool, regimen_override=job.regimen)
        lote.total_pdfs = total_pdfs

        lote.fase = "Empaquetando ZIP…"
        store.save_lote(lote)

        zip_path = settings.data_dir / f"job_{job.id}" / f"lote_{lote.numero:03d}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for pdf in lote_dir.rglob("*.pdf"):
                zf.write(pdf, arcname=pdf.relative_to(lote_dir))
        lote.zip_path = str(zip_path)

        lote.estado = EstadoExtraccion.COMPLETED
        lote.completado_en = datetime.now()
        store.save_lote(lote)
        log.info("pruebas.lote.done", extra={"job": str(job.id), "lote": lote.numero, "pdfs": total_pdfs})
        return lote

    except Exception as e:  # noqa: BLE001
        log.exception("pruebas.lote.failed")
        lote.estado = EstadoExtraccion.FAILED
        lote.mensaje_error = str(e)[:500]
        lote.completado_en = datetime.now()
        store.save_lote(lote)
        return lote


def ejecutar_extraccion_pruebas(job: Extraccion) -> None:
    """Ejecuta el job de Pruebas Rápidas lote a lote."""
    try:
        job.estado = EstadoExtraccion.RUNNING
        store.save(job)

        n_lotes = max(1, math.ceil(job.limite / job.tamano_lote))
        job.total_lotes = n_lotes
        store.save(job)
        log.info("pruebas.extraccion.start",
                 extra={"job": str(job.id), "limite": job.limite, "lotes": n_lotes})

        lotes_planificados: list[Lote] = []
        for i in range(1, n_lotes + 1):
            offset = (i - 1) * job.tamano_lote
            tamano = min(job.tamano_lote, job.limite - offset)
            lote = Lote(job_id=job.id, numero=i, offset_inicio=offset, tamano=tamano)
            store.save_lote(lote)
            lotes_planificados.append(lote)

        lote_workers = max(1, settings.lote_workers)
        usa_pdf_pool = (
            lote_workers == 1
            and settings.pdf_workers != 0
            and job.limite >= settings.pdf_parallel_threshold
        )
        pool = None
        if usa_pdf_pool:
            workers = (os.cpu_count() or 2) if settings.pdf_workers < 0 else settings.pdf_workers
            ctx = mp.get_context("fork" if os.name != "nt" else "spawn")
            pool = ctx.Pool(processes=max(1, workers))

        _lock = threading.Lock()
        total_reg, total_pdfs = 0, 0
        lotes_fallidos = 0
        afiliados_globales: set[str] = set()
        cancelado = threading.Event()

        def _run_lote(lote: Lote) -> Lote | None:
            if cancelado.is_set():
                lote.estado = EstadoExtraccion.CANCELLED
                lote.completado_en = datetime.now()
                store.save_lote(lote)
                return None
            estado_actual = store.get(job.id)
            if estado_actual and estado_actual.estado == EstadoExtraccion.CANCELLED:
                cancelado.set()
                lote.estado = EstadoExtraccion.CANCELLED
                lote.completado_en = datetime.now()
                store.save_lote(lote)
                return None

            procesado = _procesar_lote_pruebas(job, lote, pool=pool)

            with _lock:
                nonlocal total_reg, total_pdfs, lotes_fallidos
                total_reg += procesado.total_atenciones
                total_pdfs += procesado.total_pdfs
                lote_dir = settings.data_dir / f"job_{job.id}" / f"lote_{procesado.numero:03d}"
                if lote_dir.exists():
                    for sub in lote_dir.iterdir():
                        if sub.is_dir():
                            afiliados_globales.add(sub.name)
                if procesado.estado == EstadoExtraccion.FAILED:
                    lotes_fallidos += 1
                job.total_atenciones = total_reg
                job.total_afiliados = len(afiliados_globales)
                job.total_pdfs = total_pdfs
                store.save(job)

            return procesado

        with ThreadPoolExecutor(max_workers=lote_workers) as executor:
            futures = {executor.submit(_run_lote, lote): lote for lote in lotes_planificados}
            for future in as_completed(futures):
                future.result()

        if cancelado.is_set():
            job.completado_en = datetime.now()
            job.mensaje_error = "Cancelado por el usuario"
            store.save(job)
            return

        if pool is not None:
            pool.close()
            pool.join()

        job.total_afiliados = len(afiliados_globales)
        job.completado_en = datetime.now()
        if lotes_fallidos == n_lotes:
            job.estado = EstadoExtraccion.FAILED
            job.mensaje_error = "Todos los lotes fallaron"
        elif lotes_fallidos > 0:
            job.estado = EstadoExtraccion.COMPLETED
            job.mensaje_error = f"{lotes_fallidos} de {n_lotes} lotes fallaron"
        else:
            job.estado = EstadoExtraccion.COMPLETED
        store.save(job)
        log.info("pruebas.extraccion.done", extra={"job": str(job.id), "pdfs": total_pdfs})

    except Exception as e:  # noqa: BLE001
        log.exception("pruebas.extraccion.failed")
        job.estado = EstadoExtraccion.FAILED
        job.mensaje_error = str(e)[:500]
        job.completado_en = datetime.now()
        store.save(job)
