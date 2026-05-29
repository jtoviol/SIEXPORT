"""Tests del generador paralelo de PDFs."""
from datetime import date
from pathlib import Path

from efdi.infrastructure.mock_data import generar_atenciones
from efdi.pdf.parallel import generar_pdfs_paralelo


def test_genera_paralelo_produce_archivos(tmp_path: Path) -> None:
    atenciones = generar_atenciones(limite=20, desde=date(2026, 1, 1), hasta=date(2026, 5, 1))
    tareas = [(a, tmp_path / f"pdf_{i:03d}.pdf") for i, a in enumerate(atenciones)]
    n = generar_pdfs_paralelo(tareas, n_workers=2)
    assert n == 20
    pdfs = list(tmp_path.glob("*.pdf"))
    assert len(pdfs) == 20
    # Todos los PDFs deben ser archivos no vacíos
    for p in pdfs:
        assert p.stat().st_size > 500  # un PDF mínimo pesa más que esto


def test_lista_vacia_devuelve_cero() -> None:
    assert generar_pdfs_paralelo([], n_workers=2) == 0


def test_un_solo_worker_tambien_funciona(tmp_path: Path) -> None:
    atenciones = generar_atenciones(limite=5, desde=date(2026, 1, 1), hasta=date(2026, 5, 1))
    tareas = [(a, tmp_path / f"pdf_{i}.pdf") for i, a in enumerate(atenciones)]
    n = generar_pdfs_paralelo(tareas, n_workers=1)
    assert n == 5
