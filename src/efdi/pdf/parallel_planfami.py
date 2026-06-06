"""Generación paralela de PDFs de Planificación Familiar usando multiprocessing.Pool."""
import multiprocessing as mp
import os
from pathlib import Path

from efdi.domain.models import AfiliadoConPlanFamiliar
from efdi.pdf.generator_planfami import generar_pdf_planfami


def _worker(args: tuple) -> str:
    obj, path_str = args
    out = Path(path_str)
    out.parent.mkdir(parents=True, exist_ok=True)
    generar_pdf_planfami(obj, out)
    return path_str


def generar_pdfs_planfami_paralelo(
    tareas: list[tuple[AfiliadoConPlanFamiliar, Path]],
    n_workers: int | None = None,
) -> int:
    if not tareas:
        return 0
    workers = n_workers or (os.cpu_count() or 2)
    workers = max(1, min(workers, len(tareas)))
    payload = [(af, str(p)) for af, p in tareas]
    chunksize = max(50, len(payload) // (workers * 8))
    ctx = mp.get_context("fork" if os.name != "nt" else "spawn")
    with ctx.Pool(processes=workers) as pool:
        results = list(pool.imap_unordered(_worker, payload, chunksize=chunksize))
    return len(results)
