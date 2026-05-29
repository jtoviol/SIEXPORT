"""Catálogo de programas de demanda inducida cargado desde templates/programas.txt."""
from functools import lru_cache
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


@lru_cache(maxsize=1)
def cargar_catalogo() -> list[tuple[str, str]]:
    """Carga el catálogo desde programas.txt — devuelve [(cod, descripcion), ...].

    Cacheado: se carga una sola vez por proceso (importante con multiprocessing).
    """
    path = TEMPLATES_DIR / "programas.txt"
    if not path.exists():
        return []
    programas: list[tuple[str, str]] = []
    with path.open(encoding="utf-8") as f:
        next(f, None)  # saltar header
        for linea in f:
            partes = linea.rstrip("\n").split("\t")
            if len(partes) >= 2 and partes[0].strip():
                programas.append((partes[0].strip(), partes[1].strip()))
    return programas
