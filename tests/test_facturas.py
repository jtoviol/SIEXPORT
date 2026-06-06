"""Tests del endpoint GET /extractions/facturas/count (preview por factura).

Usa una FastAPI app local con solo el router de Demanda Inducida para no depender
de python-multipart (que main.py necesita por la pantalla de login).
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from efdi.api.routes import router
from efdi.infrastructure.repository import MockRepository

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def _get(params):
    return client.get("/extractions/facturas/count", params=params)


# ── Happy path ──────────────────────────────────────────────────────────────

def test_par_subsidiado_devuelve_estructura_completa() -> None:
    r = _get([("codigos", "CAB11502"), ("codigos", "FAB11502")])
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"total_filas", "documentos_unicos", "por_codigo"}
    assert body["total_filas"] > 0
    assert body["documentos_unicos"] > 0
    assert set(body["por_codigo"].keys()) == {"CAB11502", "FAB11502"}
    for item in body["por_codigo"].values():
        assert "total_filas" in item and "documentos_unicos" in item


def test_dos_pares_sub_y_cont() -> None:
    r = _get([
        ("codigos", "CAB11502"), ("codigos", "FAB11502"),
        ("codigos", "CAB11503"), ("codigos", "FAB11503"),
    ])
    assert r.status_code == 200
    body = r.json()
    assert len(body["por_codigo"]) == 4
    # total_filas global == suma de cada par
    suma = sum(item["total_filas"] for item in body["por_codigo"].values())
    assert body["total_filas"] == suma


def test_acepta_codigos_separados_por_coma() -> None:
    r = _get({"codigos": "CAB11502,FAB11502"})
    assert r.status_code == 200
    body = r.json()
    assert set(body["por_codigo"].keys()) == {"CAB11502", "FAB11502"}


def test_normaliza_lower_case_a_upper() -> None:
    r1 = _get([("codigos", "cab11502"), ("codigos", "fab11502")])
    r2 = _get([("codigos", "CAB11502"), ("codigos", "FAB11502")])
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()


# ── Validaciones ────────────────────────────────────────────────────────────

def test_rechaza_cab_sin_fab() -> None:
    r = _get({"codigos": "CAB11502"})
    assert r.status_code == 400
    assert "FAB11502" in r.json()["detail"]


def test_rechaza_fab_sin_cab() -> None:
    r = _get({"codigos": "FAB11502"})
    assert r.status_code == 400
    assert "CAB11502" in r.json()["detail"]


def test_rechaza_numeros_desparejados() -> None:
    r = _get([("codigos", "CAB11502"), ("codigos", "FAB11503")])
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "FAB11502" in detail
    assert "CAB11503" in detail


def test_rechaza_prefijo_invalido() -> None:
    r = _get([("codigos", "XYZ11502"), ("codigos", "FAB11502")])
    assert r.status_code == 400
    assert "CAB" in r.json()["detail"] and "FAB" in r.json()["detail"]


def test_rechaza_codigos_repetidos() -> None:
    r = _get([("codigos", "CAB11502"), ("codigos", "CAB11502"), ("codigos", "FAB11502")])
    assert r.status_code == 400
    assert "repetidos" in r.json()["detail"].lower()


def test_rechaza_solo_prefijo_sin_numero() -> None:
    r = _get({"codigos": "CAB,FAB"})
    assert r.status_code == 400
    assert "número" in r.json()["detail"]


def test_rechaza_lista_vacia() -> None:
    r = _get({"codigos": ""})
    assert r.status_code == 400
    assert "al menos un código" in r.json()["detail"]


# ── Mock unit-level ────────────────────────────────────────────────────────

def test_mock_es_determinista() -> None:
    """El conteo del mock debe ser estable para los mismos códigos."""
    repo = MockRepository()
    a = repo.contar_por_facturas(["CAB11502", "FAB11502"])
    b = repo.contar_por_facturas(["CAB11502", "FAB11502"])
    assert a == b


def test_mock_lista_vacia_devuelve_ceros() -> None:
    repo = MockRepository()
    out = repo.contar_por_facturas([])
    assert out == {"total_filas": 0, "documentos_unicos": 0, "por_codigo": {}}


# ════════════════════════════════════════════════════════════════════════════
# FASE 2 — Cruce de la extracción DI por factura
# ════════════════════════════════════════════════════════════════════════════

import time  # noqa: E402
from datetime import date  # noqa: E402

from efdi.domain.models import EstadoExtraccion  # noqa: E402
from efdi.infrastructure.job_store import store  # noqa: E402


def test_repo_facturas_reduce_resultado_mock() -> None:
    """Con factura el mock filtra ~50%, sin factura trae todo."""
    repo = MockRepository()
    sin = repo.obtener_atenciones(date(2026, 5, 1), date(2026, 5, 31), limite=100)
    con = repo.obtener_atenciones(
        date(2026, 5, 1), date(2026, 5, 31), limite=100,
        facturas=["CAB11502", "FAB11502"],
    )
    assert len(sin) == 100
    assert len(con) < len(sin)
    assert all(a.seq_seragil % 2 == 0 for a in con)


def test_repo_get_total_con_facturas_es_distinto() -> None:
    repo = MockRepository()
    assert repo.get_total(date(2026, 5, 1), date(2026, 5, 31)) == 25_000
    assert repo.get_total(
        date(2026, 5, 1), date(2026, 5, 31),
        facturas=["CAB11502", "FAB11502"],
    ) == 12_500


def test_post_extractions_con_factura_sub_crea_job_con_metadata() -> None:
    r = client.post("/extractions", json={
        "desde": "2026-05-01", "hasta": "2026-05-31",
        "limite": 5, "tamano_lote": 5,
        "numero_factura": "11502", "regimen": "SUBSIDIADO",
    })
    assert r.status_code == 202, r.json()
    body = r.json()
    assert body["regimen"] == "SUBSIDIADO"
    assert body["facturas"] == ["CAB11502", "FAB11502"]
    assert "SUBSIDIADO" in (body["nombre"] or "")


def test_post_extractions_normaliza_lower_y_prefijo() -> None:
    """Acepta 'cab11502' o 'subsidiado' y los normaliza a upper."""
    r = client.post("/extractions", json={
        "desde": "2026-05-01", "hasta": "2026-05-31",
        "limite": 5, "tamano_lote": 5,
        "numero_factura": "cab11502", "regimen": "subsidiado",
    })
    assert r.status_code == 202
    body = r.json()
    assert body["regimen"] == "SUBSIDIADO"
    assert body["facturas"] == ["CAB11502", "FAB11502"]


def test_post_extractions_rechaza_factura_sin_regimen() -> None:
    r = client.post("/extractions", json={
        "desde": "2026-05-01", "hasta": "2026-05-31", "limite": 5,
        "numero_factura": "11502",
    })
    assert r.status_code == 422


def test_post_extractions_rechaza_regimen_invalido() -> None:
    r = client.post("/extractions", json={
        "desde": "2026-05-01", "hasta": "2026-05-31", "limite": 5,
        "numero_factura": "11502", "regimen": "PARTICULAR",
    })
    assert r.status_code == 422


def test_post_extractions_sin_factura_funciona_igual() -> None:
    r = client.post("/extractions", json={
        "desde": "2026-05-01", "hasta": "2026-05-31",
        "limite": 5, "tamano_lote": 5,
    })
    assert r.status_code == 202
    body = r.json()
    assert body["regimen"] is None
    assert body["facturas"] is None


def test_job_con_factura_se_completa_end_to_end() -> None:
    """Crear job con factura, esperar fin, verificar que el régimen quedó persistido."""
    r = client.post("/extractions", json={
        "desde": "2026-05-01", "hasta": "2026-05-31",
        "limite": 10, "tamano_lote": 10,
        "numero_factura": "11502", "regimen": "SUBSIDIADO",
    })
    assert r.status_code == 202
    job_id = r.json()["id"]

    for _ in range(40):
        time.sleep(0.25)
        r = client.get(f"/extractions/{job_id}")
        if r.json()["estado"] in ("completed", "failed"):
            break

    final = r.json()
    assert final["estado"] == "completed", final
    assert final["regimen"] == "SUBSIDIADO"
    assert final["facturas"] == ["CAB11502", "FAB11502"]
    # Mock con factura → la mitad de los registros, así que sale entre 1 y 10
    assert 1 <= final["total_pdfs"] <= 10


def test_job_persistido_recupera_facturas_de_db() -> None:
    """Round-trip: lo que guarda job_store, lo lee igual al pedirlo de nuevo."""
    from uuid import UUID
    r = client.post("/extractions", json={
        "desde": "2026-05-01", "hasta": "2026-05-31",
        "limite": 5, "tamano_lote": 5,
        "numero_factura": "11502", "regimen": "CONTRIBUTIVO",
    })
    job_id = UUID(r.json()["id"])
    job = store.get(job_id)
    assert job is not None
    assert job.regimen == "CONTRIBUTIVO"
    assert job.facturas == ["CAB11502", "FAB11502"]
