"""Unifica los soportes PDF descargados de SIEDFASER (varios programas/lotes)
en una sola carpeta por afiliado, para facilitar la radicacion de cuentas
medicas cuando un mismo afiliado tiene soportes de mas de un programa.

USO:
    1. Copie este archivo dentro de la carpeta donde descomprimio los ZIP
       (ej. C:\\Users\\jtoviol\\Downloads\\DATA).
    2. Corra:  python unificar_soportes.py
       (o "py unificar_soportes.py" si "python" no esta en el PATH)
       Agregue --por-regimen si ademas quiere la version separada por
       SUBSIDIADO/CONTRIBUTIVO (ver mas abajo).
    3. La ventana queda esperando ENTER al terminar -- asi se ve el resumen
       antes de que se cierre.

ENTRADA ESPERADA (estructura que ya entrega SIEDFASER al descomprimir):
    DATA/<Programa>/<lote_NNN>/<TIPO_DOCUMENTO>/archivo.pdf

SALIDA (modo normal):
    DATA/SOPORTES UNIFICADOS/<TIPO_DOCUMENTO>/<Programa>_archivo.pdf

SALIDA (--por-regimen):
    DATA/SOPORTES UNIFICADOS POR REGIMEN/<SUBSIDIADO|CONTRIBUTIVO>/<TIPO_DOCUMENTO>/<Programa>_archivo.pdf

    El regimen se detecta buscando las palabras "SUBSIDIADO" o "CONTRIBUTIVO"
    en el nombre de la carpeta de cada programa (ese nombre lo escribe quien
    crea la extraccion en SIEDFASER). Si una carpeta no trae ninguna de las
    dos, sus soportes van a una carpeta aparte "SIN_REGIMEN" y se avisa en el
    resumen -- nunca se adivina ni se descarta en silencio.

Los soportes originales NO se tocan ni se borran: el script solo COPIA.
Si el mismo afiliado aparece en varios programas (del mismo regimen, en modo
--por-regimen), sus PDFs quedan juntos en una unica carpeta, cada uno con el
prefijo del programa de origen.

Sin dependencias externas -- corre con cualquier Python 3.8+, dentro o fuera
del entorno virtual del proyecto.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

INVALIDOS = re.compile(r'[\\/:*?"<>|]')
ESPACIOS = re.compile(r"\s+")

SIN_REGIMEN = "SIN_REGIMEN"
NOMBRES_SALIDA_CONOCIDOS = {"SOPORTES UNIFICADOS", "SOPORTES UNIFICADOS POR REGIMEN"}


def nombre_limpio(nombre: str) -> str:
    limpio = INVALIDOS.sub("_", nombre.strip())
    return ESPACIOS.sub("_", limpio)


def tiene_pdf(archivos: list[str]) -> bool:
    return any(a.lower().endswith(".pdf") for a in archivos)


def detectar_regimen(nombre_programa: str) -> str:
    mayus = nombre_programa.upper()
    if "SUBSIDIADO" in mayus:
        return "SUBSIDIADO"
    if "CONTRIBUTIVO" in mayus:
        return "CONTRIBUTIVO"
    return SIN_REGIMEN


@dataclass
class Trabajo:
    programa: str
    prefijo: str
    regimen: str
    carpetas_hoja: list[Path] = field(default_factory=list)


def explorar(data_root: Path, dest_folder_name: str) -> list[Trabajo]:
    excluidas = NOMBRES_SALIDA_CONOCIDOS | {dest_folder_name}
    carpetas_programa = sorted(
        p for p in data_root.iterdir() if p.is_dir() and p.name not in excluidas
    )
    if not carpetas_programa:
        print(f"ADVERTENCIA: no se encontraron carpetas de programa dentro de '{data_root}'.")
        return []

    trabajos: list[Trabajo] = []
    total = len(carpetas_programa)
    for i, carpeta_programa in enumerate(carpetas_programa, start=1):
        _imprimir_progreso("Explorando", i, total, carpeta_programa.name)

        # Cualquier carpeta, a cualquier profundidad, que tenga PDFs
        # directamente adentro se trata como "carpeta de afiliado" (o de
        # familia, en Caracterizacion Familiar) sin importar como este nombrada.
        carpetas_hoja = [
            Path(carpeta)
            for carpeta, _subdirs, archivos in os.walk(carpeta_programa)
            if tiene_pdf(archivos)
        ]
        trabajos.append(
            Trabajo(
                programa=carpeta_programa.name,
                prefijo=nombre_limpio(carpeta_programa.name),
                regimen=detectar_regimen(carpeta_programa.name),
                carpetas_hoja=carpetas_hoja,
            )
        )
    _cerrar_linea_progreso()
    return trabajos


def _imprimir_progreso(etapa: str, actual: int, total: int, detalle: str) -> None:
    pct = int((actual / total) * 100) if total else 0
    linea = f"\r{etapa}: {actual}/{total} ({pct:3d}%) - {detalle}"
    linea = linea[:120].ljust(120)
    sys.stdout.write(linea)
    sys.stdout.flush()


def _cerrar_linea_progreso() -> None:
    sys.stdout.write("\n")
    sys.stdout.flush()


_destinos_simulados: set[Path] = set()


def unificar(
    data_root: Path,
    dest_folder_name: str,
    dry_run: bool = False,
    por_regimen: bool = False,
) -> None:
    dest_root = data_root / dest_folder_name

    print(f"Carpeta de origen : {data_root}")
    print(f"Carpeta destino   : {dest_root}")
    if por_regimen:
        print("Modo: separado por REGIMEN (SUBSIDIADO / CONTRIBUTIVO / SIN_REGIMEN)")
    if dry_run:
        print("MODO PRUEBA (--dry-run): no se copiara nada, solo se muestra el conteo.")
    print()

    print("Explorando carpetas (puede tardar si hay muchos archivos)...")
    trabajos = explorar(data_root, dest_folder_name)
    total_hojas = sum(len(t.carpetas_hoja) for t in trabajos)
    print(f"Encontradas {total_hojas} carpetas de afiliado/familia en {len(trabajos)} programa(s).")

    programas_sin_regimen = sorted({t.programa for t in trabajos if t.regimen == SIN_REGIMEN})
    if por_regimen and programas_sin_regimen:
        print()
        print("ADVERTENCIA: no se pudo detectar el regimen de estas carpetas")
        print("(no traen 'SUBSIDIADO' ni 'CONTRIBUTIVO' en el nombre); sus soportes")
        print(f"van a la carpeta '{SIN_REGIMEN}':")
        for p in programas_sin_regimen:
            print(f"  - {p}")
    print()

    if not dry_run:
        dest_root.mkdir(parents=True, exist_ok=True)

    total_copiados = 0
    total_renombrados = 0
    afiliados_vistos: dict[tuple[str, str], set[str]] = {}
    resumen_por_programa: dict[str, int] = {}
    resumen_por_regimen: dict[str, int] = {}
    procesadas = 0

    for trabajo in trabajos:
        pdfs_de_este_programa = 0
        carpeta_regimen = trabajo.regimen if por_regimen else ""

        for carpeta_afiliado in trabajo.carpetas_hoja:
            procesadas += 1
            if procesadas % 25 == 0 or procesadas == total_hojas:
                _imprimir_progreso("Unificando", procesadas, total_hojas, trabajo.programa)

            nombre_afiliado = carpeta_afiliado.name
            dest_afiliado_dir = (
                dest_root / carpeta_regimen / nombre_afiliado
                if por_regimen
                else dest_root / nombre_afiliado
            )

            clave_afiliado = (carpeta_regimen, nombre_afiliado)
            afiliados_vistos.setdefault(clave_afiliado, set()).add(trabajo.programa)

            if not dry_run:
                dest_afiliado_dir.mkdir(parents=True, exist_ok=True)

            pdfs = sorted(p for p in carpeta_afiliado.iterdir() if p.suffix.lower() == ".pdf")
            for pdf in pdfs:
                nombre_destino = f"{trabajo.prefijo}_{pdf.name}"
                ruta_destino = dest_afiliado_dir / nombre_destino

                if ruta_destino.exists() or (dry_run and ruta_destino in _destinos_simulados):
                    # Choque de nombre (mismo programa + mismo nombre de archivo ya copiado): se agrega consecutivo.
                    base = pdf.stem
                    ext = pdf.suffix
                    contador = 2
                    while ruta_destino.exists() or (dry_run and ruta_destino in _destinos_simulados):
                        nombre_destino = f"{trabajo.prefijo}_{base}_{contador}{ext}"
                        ruta_destino = dest_afiliado_dir / nombre_destino
                        contador += 1
                    total_renombrados += 1

                if dry_run:
                    _destinos_simulados.add(ruta_destino)
                else:
                    shutil.copy2(pdf, ruta_destino)

                total_copiados += 1
                pdfs_de_este_programa += 1

        resumen_por_programa[trabajo.programa] = pdfs_de_este_programa
        if por_regimen:
            resumen_por_regimen[trabajo.regimen] = (
                resumen_por_regimen.get(trabajo.regimen, 0) + pdfs_de_este_programa
            )

    if total_hojas:
        _cerrar_linea_progreso()

    afiliados_con_varios = sum(1 for progs in afiliados_vistos.values() if len(progs) > 1)

    print()
    print("===== Resumen =====")
    for programa in sorted(resumen_por_programa):
        print(f"  {programa:<45} {resumen_por_programa[programa]:>6} PDF")
    print("-------------------------------------------")
    if por_regimen:
        for regimen in sorted(resumen_por_regimen):
            print(f"  Total {regimen:<20} : {resumen_por_regimen[regimen]:>6} PDF")
        print("-------------------------------------------")
    print(f"Afiliados/familias unificados : {len(afiliados_vistos)}")
    print(f"  - con soportes de 2+ programas: {afiliados_con_varios}")
    print(f"PDFs copiados                 : {total_copiados}")
    if total_renombrados:
        print(f"PDFs con consecutivo agregado (choque de nombre): {total_renombrados}")

    print()
    if dry_run:
        print("Esto fue una PRUEBA. Corra sin --dry-run para copiar de verdad.")
    else:
        print(f"Listo. Revise: {dest_root}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data-root",
        default=str(Path(__file__).resolve().parent),
        help="Carpeta raiz donde estan las carpetas de cada programa (por defecto, la carpeta de este script)",
    )
    parser.add_argument(
        "--dest-name",
        default=None,
        help="Nombre de la carpeta de salida (por defecto: 'SOPORTES UNIFICADOS', o "
        "'SOPORTES UNIFICADOS POR REGIMEN' si se usa --por-regimen)",
    )
    parser.add_argument(
        "--por-regimen",
        action="store_true",
        help="Separa el resultado en subcarpetas SUBSIDIADO / CONTRIBUTIVO / SIN_REGIMEN",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Solo muestra que haria, sin copiar nada"
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="No espera ENTER al final (para uso automatizado)",
    )
    args = parser.parse_args()

    data_root = Path(args.data_root)
    if not data_root.exists():
        print(f"ERROR: no existe la carpeta de origen: {data_root}")
        sys.exit(1)

    dest_name = args.dest_name or (
        "SOPORTES UNIFICADOS POR REGIMEN" if args.por_regimen else "SOPORTES UNIFICADOS"
    )

    unificar(data_root.resolve(), dest_name, args.dry_run, args.por_regimen)

    if not args.no_interactive:
        print()
        input("Presione ENTER para cerrar esta ventana...")


if __name__ == "__main__":
    main()
