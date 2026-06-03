"""Orquestador Gestión Captación: divide en lotes → query → agrupar → PDFs → zip."""
import logging
import math
import multiprocessing as mp
import os
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from efdi.config import settings
from efdi.domain.models import AfiliadoConCaptacion, EstadoExtraccion, Extraccion, Lote
from efdi.domain.services import agrupar_por_afiliado_captacion
from efdi.infrastructure.job_store import store
from efdi.infrastructure.repository_captacion import get_captacion_repository
from efdi.pdf.generator_captacion import generar_pdf_captacion
from efdi.pdf.parallel_captacion import _worker as pdf_worker_captacion

log = logging.getLogger(__name__)


def _generar_pdfs_captacion(
    tareas: list[tuple[AfiliadoConCaptacion, Path]],
    pool: "mp.pool.Pool | None" = None,
) -> int:
    n = len(tareas)
    if settings.pdf_workers == 0 or n < settings.pdf_parallel_threshold or pool is None:
        for afiliado, path in tareas:
            path.parent.mkdir(parents=True, exist_ok=True)
            generar_pdf_captacion(afiliado, path)
        return n
    dirs = {p.parent for _, p in tareas}
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    payload = [(af, str(p)) for af, p in tareas]
    chunksize = max(20, n // (pool._processes * 8))  # type: ignore[attr-defined]
    results = list(pool.imap_unordered(pdf_worker_captacion, payload, chunksize=chunksize))
    return len(results)


def _procesar_lote_captacion(job: Extraccion, lote: Lote, pool: "mp.pool.Pool | None" = None) -> Lote:
    log.info("captacion.lote.start", extra={"job": str(job.id), "lote": lote.numero})
    lote.estado = EstadoExtraccion.RUNNING
    lote.iniciado_en = datetime.now()
    store.save_lote(lote)

    try:
        lote.fase = "Consultando base de datos…"
        store.save_lote(lote)
        repo = get_captacion_repository()
        registros = repo.obtener_registros(
            desde=job.desde,
            hasta=job.hasta,
            limite=lote.tamano,
            offset=lote.offset_inicio,
        )
        lote.total_atenciones = len(registros)

        if not registros:
            lote.fase = ""
            lote.estado = EstadoExtraccion.COMPLETED
            lote.completado_en = datetime.now()
            store.save_lote(lote)
            return lote

        afiliados = agrupar_por_afiliado_captacion(registros)
        lote.total_afiliados = len(afiliados)

        lote.fase = f"Generando PDFs ({len(afiliados)} afiliados)…"
        store.save_lote(lote)

        lote_dir = settings.data_dir / f"job_{job.id}" / f"lote_{lote.numero:03d}"
        lote_dir.mkdir(parents=True, exist_ok=True)

        tareas: list[tuple[AfiliadoConCaptacion, Path]] = []
        for afiliado in afiliados:
            pdf_path = lote_dir / afiliado.doc_key / f"{afiliado.pdf_key}.pdf"
            tareas.append((afiliado, pdf_path))

        total_pdfs = _generar_pdfs_captacion(tareas, pool=pool)
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
        log.info("captacion.lote.done", extra={"job": str(job.id), "lote": lote.numero, "pdfs": total_pdfs})
        return lote

    except Exception as e:  # noqa: BLE001
        log.exception("captacion.lote.failed")
        lote.estado = EstadoExtraccion.FAILED
        lote.mensaje_error = str(e)[:500]
        lote.completado_en = datetime.now()
        store.save_lote(lote)
        return lote


def ejecutar_extraccion_captacion(job: Extraccion) -> None:
    """Ejecuta el job de Gestión Captación completo lote a lote."""
    try:
        job.estado = EstadoExtraccion.RUNNING
        store.save(job)

        n_lotes = max(1, math.ceil(job.limite / job.tamano_lote))
        job.total_lotes = n_lotes
        store.save(job)
        log.info("captacion.extraccion.start", extra={"job": str(job.id), "limite": job.limite, "lotes": n_lotes})

        lotes_planificados: list[Lote] = []
        for i in range(1, n_lotes + 1):
            offset = (i - 1) * job.tamano_lote
            tamano = min(job.tamano_lote, job.limite - offset)
            lote = Lote(job_id=job.id, numero=i, offset_inicio=offset, tamano=tamano)
            store.save_lote(lote)
            lotes_planificados.append(lote)

        lote_workers = max(1, settings.lote_workers)
        usa_pdf_pool = lote_workers == 1 and settings.pdf_workers != 0 and job.limite >= settings.pdf_parallel_threshold
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

            procesado = _procesar_lote_captacion(job, lote, pool=pool)

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
        log.info("captacion.extraccion.done", extra={"job": str(job.id), "pdfs": total_pdfs})

    except Exception as e:  # noqa: BLE001
        log.exception("captacion.extraccion.failed")
        job.estado = EstadoExtraccion.FAILED
        job.mensaje_error = str(e)[:500]
        job.completado_en = datetime.now()
        store.save(job)
