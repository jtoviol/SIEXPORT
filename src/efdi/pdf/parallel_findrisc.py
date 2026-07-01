"""Generación paralela de PDFs FINDRISC usando multiprocessing.Pool."""
import multiprocessing as mp
import os
from pathlib import Path

from efdi.domain.models import AfiliadoConFindrisc
from efdi.pdf.generator_findrisc import generar_pdf_findrisc


def _worker(args: tuple) -> str:
    # Tupla puede venir con 2 o 3 elementos (compat con llamadas viejas)
    if len(args) == 3:
        obj, path_str, regimen_override = args
    else:
        obj, path_str = args
        regimen_override = None
    out = Path(path_str)
    out.parent.mkdir(parents=True, exist_ok=True)
    generar_pdf_findrisc(obj, out, regimen_override=regimen_override)
    return path_str


def generar_pdfs_findrisc_paralelo(
    tareas: list[tuple[AfiliadoConFindrisc, Path]],
    n_workers: int | None = None,
    regimen_override: str | None = None,
) -> int:
    if not tareas:
        return 0
    workers = n_workers or (os.cpu_count() or 2)
    workers = max(1, min(workers, len(tareas)))
    payload = [(af, str(p), regimen_override) for af, p in tareas]
    chunksize = max(50, len(payload) // (workers * 8))
    ctx = mp.get_context("fork" if os.name != "nt" else "spawn")
    with ctx.Pool(processes=workers) as pool:
        results = list(pool.imap_unordered(_worker, payload, chunksize=chunksize))
    return len(results)
