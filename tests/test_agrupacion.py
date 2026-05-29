"""Tests de la lógica de agrupación por afiliado."""
from datetime import date

from efdi.domain.services import agrupar_por_afiliado
from efdi.infrastructure.mock_data import generar_atenciones


def test_agrupa_correctamente() -> None:
    atenciones = generar_atenciones(limite=25, desde=date(2026, 1, 1), hasta=date(2026, 5, 1))
    grupos = agrupar_por_afiliado(atenciones)

    # Suma de atenciones agrupadas == total original
    total = sum(g.total_atenciones for g in grupos)
    assert total == len(atenciones)

    # Cada grupo tiene doc_key único
    keys = [g.doc_key for g in grupos]
    assert len(keys) == len(set(keys))

    # Cada doc_key tiene formato TIPO_NUMERO
    for g in grupos:
        assert "_" in g.doc_key
        tipo, num = g.doc_key.split("_", 1)
        assert tipo in {"CC", "TI", "MS", "RC", "CE", "PA"}
        assert num.isdigit()
