"""Helper compartido por los endpoints `/extractions/{id}/files` de todos los
módulos: capea cuántos archivos se devuelven para que una extracción con
cientos de miles de PDFs no congele al navegador tratando de pintar un árbol
gigante de una sola vez. Descargar el .zip completo sigue sin límite."""
from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path
from typing import Callable

LIMITE_ARCHIVOS_DEFAULT = 2000
LIMITE_CARPETAS_DEFAULT = 500


def capear_folders(folders: list[dict], limite: int = LIMITE_ARCHIVOS_DEFAULT) -> dict:
    """Recibe `folders` ya armado ([{"name":..., "files":[...]}, ...]) y
    devuelve el dict final de respuesta, recortando el total de archivos al
    límite indicado (se recorta carpeta por carpeta, sin partir el orden)."""
    total_real = sum(len(f["files"]) for f in folders)
    restante = limite
    folders_cap: list[dict] = []
    for f in folders:
        if restante <= 0:
            break
        tomados = f["files"][:restante]
        folders_cap.append({**f, "files": tomados})
        restante -= len(tomados)
    total_devuelto = sum(len(f["files"]) for f in folders_cap)
    return {
        "folders": folders_cap,
        "total": total_devuelto,
        "total_real": total_real,
        "truncado": total_devuelto < total_real,
    }


def listar_arbol_anidado(
    job_dir: Path, *, job_id: str, limit: int = LIMITE_CARPETAS_DEFAULT, offset: int = 0,
) -> dict:
    """Para estructura `job_dir/lote_NNN/<carpeta>/*.pdf` (una subcarpeta por
    afiliado/familia dentro de cada lote — Soporte Unificado, Pruebas Rápidas).

    En Docker Desktop (Windows) cada syscall de filesystem contra un bind
    mount tiene latencia alta (~10ms medidos). Con miles de subcarpetas,
    entrar a CADA UNA para listar sus PDFs puede tardar minutos aunque solo
    se vayan a mostrar 500. Por eso acá se listan los NOMBRES de carpeta
    primero (barato: un solo listado por lote) para saber el total real y
    decidir la página, y solo se abre+stat las carpetas que de verdad entran
    en esa página."""
    lote_dirs = sorted(
        e.path for e in os.scandir(job_dir) if e.is_dir() and e.name.startswith("lote_")
    )

    ubicacion: dict[str, str] = {}
    for lote_path in lote_dirs:
        with os.scandir(lote_path) as it:
            for e in it:
                if e.is_dir():
                    ubicacion[e.name] = lote_path

    claves = sorted(ubicacion.keys())
    total_folders = len(claves)
    pagina = claves[offset:offset + limit]

    folders = []
    for nombre_carpeta in pagina:
        lote_path = ubicacion[nombre_carpeta]
        lote_name = os.path.basename(lote_path)
        carpeta = os.path.join(lote_path, nombre_carpeta)
        archivos = sorted(
            (
                {
                    "name": e.name, "doc_key": os.path.splitext(e.name)[0],
                    "size": e.stat().st_size, "lote": lote_name,
                }
                for e in os.scandir(carpeta) if e.name.endswith(".pdf")
            ),
            key=lambda x: x["name"],
        )
        folders.append({"name": nombre_carpeta, "doc_key": nombre_carpeta, "files": archivos})

    return {
        "job_id": job_id,
        "folders": folders,
        "total": sum(len(f["files"]) for f in folders),
        "total_folders": total_folders,
        "offset": offset,
        "truncado": offset + len(pagina) < total_folders,
    }


def listar_arbol_plano(
    job_dir: Path, *, job_id: str,
    agrupar: Callable[[str], "str | None"],
    limite: int = LIMITE_ARCHIVOS_DEFAULT,
) -> dict:
    """Para estructura `job_dir/lote_NNN/<archivo>.pdf` (PDFs sueltos
    directamente dentro de cada lote, sin subcarpeta por afiliado — DI,
    FINDRISC, PlanFami, Gestión Captación, Vacunación, Educación Grupal).

    `agrupar(nombre_archivo)` decide en qué "carpeta" del árbol cae cada
    archivo (ej. el tipo de documento "CC"/"TI") o `None` para descartarlo.

    Antes se le sacaba `.stat()` a TODOS los archivos antes de recortar al
    límite — con extracciones de cientos de miles de PDFs eso solo, sin abrir
    ninguna carpeta extra, ya podía tardar minutos. Acá se listan los
    nombres primero (barato, un solo scandir por lote) y el `stat()` —la
    parte cara— solo se hace para los archivos que sobreviven el recorte."""
    lote_dirs = sorted(
        e.path for e in os.scandir(job_dir) if e.is_dir() and e.name.startswith("lote_")
    )

    agrupado: dict[str, list[dict]] = defaultdict(list)
    for lote_path in lote_dirs:
        lote_name = os.path.basename(lote_path)
        with os.scandir(lote_path) as it:
            for e in it:
                if not e.name.endswith(".pdf"):
                    continue
                clave = agrupar(e.name)
                if clave is None:
                    continue
                agrupado[clave].append({"name": e.name, "lote": lote_name, "_path": e.path})

    total_real = sum(len(v) for v in agrupado.values())
    restante = limite
    folders = []
    for clave in sorted(agrupado.keys()):
        if restante <= 0:
            break
        candidatos = sorted(agrupado[clave], key=lambda x: x["name"])
        tomados = candidatos[:restante]
        restante -= len(tomados)
        archivos = [
            {
                "name": it["name"], "doc_key": os.path.splitext(it["name"])[0],
                "lote": it["lote"], "size": os.stat(it["_path"]).st_size,
            }
            for it in tomados
        ]
        folders.append({"name": clave, "files": archivos})

    total_devuelto = sum(len(f["files"]) for f in folders)
    return {
        "job_id": job_id,
        "folders": folders,
        "total": total_devuelto,
        "total_real": total_real,
        "truncado": total_devuelto < total_real,
    }
