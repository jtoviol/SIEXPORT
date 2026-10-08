"""Excepciones compartidas de la capa de infraestructura.

Permiten distinguir, desde las rutas, un error real de infraestructura
(timeout de conexión, SQL Server caído, credenciales vencidas) de un
resultado legítimo de "0 registros" — algo que antes se confundía porque
`get_total()` devolvía 0 en ambos casos.
"""
from __future__ import annotations


class RepositorioNoDisponibleError(RuntimeError):
    """La consulta no pudo completarse por un problema de infraestructura
    (conexión, timeout, driver, etc.), no porque no haya datos.

    Las rutas deben traducir esto a un 503 con mensaje claro, nunca a un
    400 de "no se encontraron registros"."""
