"""Orquestador del job: dividir en lotes → query → agrupar → PDFs → zip por lote."""
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
from efdi.domain.models import AfiliadoConAtenciones, EstadoExtraccion, Extraccion, Lote
from efdi.domain.services import agrupar_por_afiliado
from efdi.infrastructure.job_store import store
from efdi.infrastructure.repository import get_repository
from efdi.pdf.generator import generar_pdf_afiliado
from efdi.pdf.parallel import _worker as pdf_worker

log = logging.getLogger(__name__)


def _generar_pdfs_por_afiliado(
    tareas: list[tuple[AfiliadoConAtenciones, Path]],
    pool: "mp.pool.Pool | None" = None,
) -> int:
    """Genera un PDF (multi-página) por afiliado. Devuelve cantidad de PDFs."""
    n = len(tareas)
    if settings.pdf_workers == 0 or n < settings.pdf_parallel_threshold or pool is None:
        # Secuencial
        for afiliado, path in tareas:
            path.parent.mkdir(parents=True, exist_ok=True)
            generar_pdf_afiliado(afiliado, path)
        return n
    # Paralelo
    dirs = {p.parent for _, p in tareas}
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    payload = [(af, str(p)) for af, p in tareas]
    chunksize = max(20, n // (pool._processes * 8))  # type: ignore[attr-defined]
    results = list(pool.imap_unordered(pdf_worker, payload, chunksize=chunksize))
    return len(results)


def _procesar_lote(job: Extraccion, lote: Lote, pool: "mp.pool.Pool | None" = None) -> Lote:
    """Procesa un solo lote: query → PDFs → zip. Devuelve el lote actualizado."""
    log.info("lote.start", extra={"job": str(job.id), "lote": lote.numero})
    lote.estado = EstadoExtraccion.RUNNING
    lote.iniciado_en = datetime.now()
    store.save_lote(lote)

    try:
        repo = get_repository()
        atenciones = repo.obtener_atenciones(
            desde=job.desde,
            hasta=job.hasta,
            limite=lote.tamano,
            offset=lote.offset_inicio,
        )
        lote.total_atenciones = len(atenciones)

        if not atenciones:
            # Lote vacío (rango sin datos en ese offset) — se marca completed con 0
            lote.estado = EstadoExtraccion.COMPLETED
            lote.completado_en = datetime.now()
            store.save_lote(lote)
            store.save_atenciones(job.id, atenciones)
            return lote

        # Si es el primer lote, guarda muestra para vista de detalle
        if lote.numero == 1:
            store.save_atenciones(job.id, atenciones)

        afiliados = agrupar_por_afiliado(atenciones)
        lote.total_afiliados = len(afiliados)

        # Directorio del lote
        lote_dir = settings.data_dir / f"job_{job.id}" / f"lote_{lote.numero:03d}"
        lote_dir.mkdir(parents=True, exist_ok=True)

        # 1 PDF por afiliado, multipágina (una página por atención del afiliado)
        tareas: list[tuple[AfiliadoConAtenciones, Path]] = []
        for afiliado in afiliados:
            # Carpeta por afiliado, PDF nombrado con doc + fecha
            pdf_path = lote_dir / afiliado.doc_key / f"{afiliado.pdf_key}.pdf"
            tareas.append((afiliado, pdf_path))

        total_pdfs = _generar_pdfs_por_afiliado(tareas, pool=pool)
        lote.total_pdfs = total_pdfs
        log.info(
            "lote.pdfs_done",
            extra={
                "job": str(job.id), "lote": lote.numero,
                "afiliados": len(afiliados), "atenciones": len(atenciones), "pdfs": total_pdfs,
                "modo": "paralelo_pool" if pool else "secuencial",
            },
        )

        # ZIP del lote — estructura: <doc_key>/<doc_key>.pdf
        zip_path = settings.data_dir / f"job_{job.id}" / f"lote_{lote.numero:03d}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for pdf in lote_dir.rglob("*.pdf"):
                zf.write(pdf, arcname=pdf.relative_to(lote_dir))
        lote.zip_path = str(zip_path)

        lote.estado = EstadoExtraccion.COMPLETED
        lote.completado_en = datetime.now()
        store.save_lote(lote)
        log.info(
            "lote.done",
            extra={"job": str(job.id), "lote": lote.numero, "pdfs": total_pdfs},
        )
        return lote

    except Exception as e:  # noqa: BLE001
        log.exception("lote.failed")
        lote.estado = EstadoExtraccion.FAILED
        lote.mensaje_error = str(e)[:500]
        lote.completado_en = datetime.now()
        store.save_lote(lote)
        return lote


def ejecutar_extraccion(job: Extraccion) -> None:
    """Ejecuta el job completo lote a lote. Actualiza estado en cada paso."""
    try:
        job.estado = EstadoExtraccion.RUNNING
        store.save(job)

        # Cuántos lotes
        n_lotes = max(1, math.ceil(job.limite / job.tamano_lote))
        job.total_lotes = n_lotes
        store.save(job)
        log.info(
            "extraccion.start",
            extra={"job": str(job.id), "limite": job.limite, "lotes": n_lotes},
        )

        # Crear lotes en SQLite (estado pending)
        lotes_planificados: list[Lote] = []
        for i in range(1, n_lotes + 1):
            offset = (i - 1) * job.tamano_lote
            tamano = min(job.tamano_lote, job.limite - offset)
            lote = Lote(
                job_id=job.id,
                numero=i,
                offset_inicio=offset,
                tamano=tamano,
            )
            store.save_lote(lote)
            lotes_planificados.append(lote)

        # Con lotes en paralelo el pool interno de PDFs se desactiva para no saturar la máquina
        # (el paralelismo viene del nivel de lote, no del nivel de PDF)
        lote_workers = max(1, settings.lote_workers)
        usa_pdf_pool = lote_workers == 1 and settings.pdf_workers != 0 and job.limite >= settings.pdf_parallel_threshold
        pool = None
        if usa_pdf_pool:
            workers = (os.cpu_count() or 2) if settings.pdf_workers < 0 else settings.pdf_workers
            ctx = mp.get_context("fork" if os.name != "nt" else "spawn")
            pool = ctx.Pool(processes=max(1, workers))
            log.info("extraccion.pool_started", extra={"job": str(job.id), "pdf_workers": workers})

        log.info("extraccion.lote_workers", extra={"job": str(job.id), "lote_workers": lote_workers})

        # Estado compartido entre hilos (protegido por lock)
        _lock = threading.Lock()
        total_at, total_pdfs = 0, 0
        lotes_fallidos = 0
        afiliados_globales: set[str] = set()
        cancelado = threading.Event()

        def _run_lote(lote: Lote) -> Lote | None:
            """Worker de hilo: procesa un lote y actualiza el job en vivo."""
            if cancelado.is_set():
                lote.estado = EstadoExtraccion.CANCELLED
                lote.completado_en = datetime.now()
                store.save_lote(lote)
                return None

            # Check cooperativo de cancelación
            estado_actual = store.get(job.id)
            if estado_actual and estado_actual.estado == EstadoExtraccion.CANCELLED:
                cancelado.set()
                lote.estado = EstadoExtraccion.CANCELLED
                lote.completado_en = datetime.now()
                store.save_lote(lote)
                return None

            procesado = _procesar_lote(job, lote, pool=pool)

            with _lock:
                nonlocal total_at, total_pdfs, lotes_fallidos
                total_at += procesado.total_atenciones
                total_pdfs += procesado.total_pdfs
                lote_dir = settings.data_dir / f"job_{job.id}" / f"lote_{procesado.numero:03d}"
                if lote_dir.exists():
                    for sub in lote_dir.iterdir():
                        if sub.is_dir():
                            afiliados_globales.add(sub.name)
                if procesado.estado == EstadoExtraccion.FAILED:
                    lotes_fallidos += 1
                job.total_atenciones = total_at
                job.total_afiliados = len(afiliados_globales)
                job.total_pdfs = total_pdfs
                store.save(job)

            return procesado

        datos_agotados = False
        with ThreadPoolExecutor(max_workers=lote_workers) as executor:
            futures = {executor.submit(_run_lote, lote): lote for lote in lotes_planificados}
            for future in as_completed(futures):
                procesado = future.result()
                if procesado is None:
                    continue
                if (procesado.total_atenciones < futures[future].tamano
                        and procesado.estado == EstadoExtraccion.COMPLETED):
                    datos_agotados = True
                    log.info("extraccion.early_stop", extra={"job": str(job.id), "after_lote": procesado.numero})

        if cancelado.is_set():
            job.completado_en = datetime.now()
            job.mensaje_error = "Cancelado por el usuario"
            store.save(job)
            return

        if datos_agotados:
            log.info("extraccion.data_exhausted", extra={"job": str(job.id)})

        # Cerrar pool de PDFs si lo usamos
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
        log.info(
            "extraccion.done",
            extra={
                "job": str(job.id),
                "lotes_ok": n_lotes - lotes_fallidos,
                "lotes_fallidos": lotes_fallidos,
                "pdfs": total_pdfs,
            },
        )

    except Exception as e:  # noqa: BLE001
        log.exception("extraccion.failed")
        job.estado = EstadoExtraccion.FAILED
        job.mensaje_error = str(e)[:500]
        job.completado_en = datetime.now()
        store.save(job)
