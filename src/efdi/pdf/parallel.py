"""Generación paralela de PDFs usando multiprocessing.Pool.

Diseñado para que sea picklable: el worker recibe (AfiliadoConAtenciones, str_path)
y delega al `generar_pdf_afiliado` regular.
"""
import multiprocessing as mp
import os
from pathlib import Path

from efdi.domain.models import AfiliadoConAtenciones
from efdi.pdf.generator import generar_pdf_afiliado


def _worker(args: tuple) -> str:
    """Worker que corre en un proceso separado."""
    obj, path_str = args
    out = Path(path_str)
    out.parent.mkdir(parents=True, exist_ok=True)
    generar_pdf_afiliado(obj, out)
    return path_str


def generar_pdfs_paralelo(
    tareas: list[tuple[AfiliadoConAtenciones, Path]],
    n_workers: int | None = None,
) -> int:
    """Genera todos los PDFs usando un Pool de procesos.

    Devuelve la cantidad generada con éxito. Errores individuales se propagan.
    Si n_workers es None, usa TODOS los cores de la CPU (no tope artificial).
    """
    if not tareas:
        return 0

    # Usar TODOS los cores disponibles (PDF gen es CPU-bound, no I/O-bound)
    workers = n_workers or (os.cpu_count() or 2)
    workers = max(1, min(workers, len(tareas)))

    # Convertir Path a str (Path no es 100% portable en pickle entre OS)
    payload = [(at, str(p)) for at, p in tareas]

    # chunksize: balance entre overhead de IPC y distribución de carga
    # Más alto = menos overhead pero peor balanceo. 50 PDFs por chunk va bien.
    chunksize = max(50, len(payload) // (workers * 8))

    # fork es más rápido que spawn (no re-importa módulos), pero solo Linux/macOS
    ctx = mp.get_context("fork" if os.name != "nt" else "spawn")
    with ctx.Pool(processes=workers) as pool:
        # imap_unordered es más rápido cuando no nos importa el orden
        results = list(pool.imap_unordered(_worker, payload, chunksize=chunksize))

    return len(results)
