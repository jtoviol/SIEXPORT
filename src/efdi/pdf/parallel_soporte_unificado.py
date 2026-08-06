"""Worker multiproceso para Soporte Unificado.

No tiene generador propio: despacha cada tarea al generador del módulo que
corresponde según su id. La tarea llega como (mod_id, obj, ruta, regimen).

`obj` es el objeto que espera cada generador:
- pruebas-rapidas → un AfiliadoConPruebasRapidas (1 PDF consolidado por persona)
- caracterizacion-familiar → una FamiliaCaracterizada (PDF en carpeta del jefe)
- el resto → el objeto-afiliado agrupado del módulo
"""
from __future__ import annotations

from pathlib import Path

from efdi.pdf.generator import generar_pdf_afiliado
from efdi.pdf.generator_captacion import generar_pdf_captacion
from efdi.pdf.generator_caracterizacion import generar_pdf_caracterizacion
from efdi.pdf.generator_educacion_grupal import generar_pdf_educacion_grupal
from efdi.pdf.generator_findrisc import generar_pdf_findrisc
from efdi.pdf.generator_planfami import generar_pdf_planfami
from efdi.pdf.generator_pruebas import generar_pdf_pruebas_consolidado
from efdi.pdf.generator_vacunacion import generar_pdf_vacunacion


# Wrappers con firma uniforme (obj, path, regimen). Los 6 que aceptan
# regimen_override reciben el régimen de la corrida; Caracterización (régimen del
# jefe) y Vacunación (régimen del Excel) lo ignoran.
def _g_di(obj, path, reg):               generar_pdf_afiliado(obj, path, regimen_override=reg)
def _g_findrisc(obj, path, reg):         generar_pdf_findrisc(obj, path, regimen_override=reg)
def _g_planfami(obj, path, reg):         generar_pdf_planfami(obj, path, regimen_override=reg)
def _g_pruebas(obj, path, reg):          generar_pdf_pruebas_consolidado(obj, path, regimen_override=reg)
def _g_captacion(obj, path, reg):        generar_pdf_captacion(obj, path, regimen_override=reg)
def _g_educacion(obj, path, reg):        generar_pdf_educacion_grupal(obj, path, regimen_override=reg)
def _g_caracterizacion(obj, path, reg):  generar_pdf_caracterizacion(obj, path)
def _g_vacunacion(obj, path, reg):       generar_pdf_vacunacion(obj, path)


_GENERADORES = {
    "demanda-inducida":         _g_di,
    "findrisc":                 _g_findrisc,
    "planificacion-familiar":   _g_planfami,
    "pruebas-rapidas":          _g_pruebas,
    "gestion-captacion":        _g_captacion,
    "educacion-grupal":         _g_educacion,
    "caracterizacion-familiar": _g_caracterizacion,
    "vacunacion":               _g_vacunacion,
}


def _worker(payload: tuple) -> str:
    """payload = (mod_id, obj, ruta_str, regimen). Genera el PDF y devuelve la ruta."""
    mod_id, obj, ruta_str, regimen = payload
    path = Path(ruta_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    _GENERADORES[mod_id](obj, path, regimen)
    return ruta_str
