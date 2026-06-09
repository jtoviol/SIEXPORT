"""Worker para generar PDFs de Vacunación en paralelo con multiprocessing.

Mismo patrón que parallel.py / parallel_findrisc.py — un proceso por chunk de
tareas, comunicación vía pool.imap_unordered.
"""
from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path

from efdi.domain.models import AfiliadoConVacunas
from efdi.pdf.generator_vacunacion import generar_pdf_vacunacion


def _worker(args: tuple) -> str:
    """Worker top-level (debe serlo para que multiprocessing pueda picklearlo).
    Acepta tupla de 2 elementos (afiliado, path_str). No hay regimen_override en
    Vacunación porque el régimen viene del propio Excel.
    """
    obj, path_str = args
    out = Path(path_str)
    out.parent.mkdir(parents=True, exist_ok=True)
    generar_pdf_vacunacion(obj, out)
    return path_str


def generar_pdfs_vacunacion_paralelo(
    tareas: list[tuple[AfiliadoConVacunas, Path]],
    n_workers: int | None = None,
) -> int:
    """Genera N PDFs en paralelo. Devuelve cantidad generada."""
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
