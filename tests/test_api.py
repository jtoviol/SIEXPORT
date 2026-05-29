"""Tests de los endpoints REST."""
import time

from fastapi.testclient import TestClient

from efdi.main import app

client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["modo"] == "mock"


def test_swagger_disponible() -> None:
    r = client.get("/docs")
    assert r.status_code == 200


def test_crear_extraccion_flow_completo() -> None:
    r = client.post("/extractions", json={
        "desde": "2026-04-01", "hasta": "2026-05-28", "limite": 10, "tamano_lote": 10,
    })
    assert r.status_code == 202
    job_id = r.json()["id"]

    # Esperar a que termine
    for _ in range(30):
        time.sleep(0.5)
        r = client.get(f"/extractions/{job_id}")
        if r.json()["estado"] in ("completed", "failed"):
            break

    final = r.json()
    assert final["estado"] == "completed", final
    assert final["total_atenciones"] > 0
    assert final["total_pdfs"] == final["total_atenciones"]
    assert final["total_lotes"] == 1

    # Descargar zip global (mega-zip combinado de lotes)
    r = client.get(f"/extractions/{job_id}/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"


def test_extraccion_con_multiples_lotes() -> None:
    """30 registros en lotes de 10 → 3 lotes."""
    r = client.post("/extractions", json={
        "desde": "2026-04-01", "hasta": "2026-05-28", "limite": 30, "tamano_lote": 10,
    })
    assert r.status_code == 202
    job_id = r.json()["id"]

    for _ in range(60):
        time.sleep(0.5)
        r = client.get(f"/extractions/{job_id}")
        if r.json()["estado"] in ("completed", "failed"):
            break

    final = r.json()
    assert final["estado"] == "completed", final
    assert final["total_lotes"] == 3

    # Lista de lotes
    r = client.get(f"/extractions/{job_id}/lotes")
    assert r.status_code == 200
    lotes = r.json()
    assert len(lotes) == 3
    assert all(l["estado"] == "completed" for l in lotes)
    assert sum(l["total_atenciones"] for l in lotes) == final["total_atenciones"]

    # Descargar lote individual
    r = client.get(f"/extractions/{job_id}/lotes/1/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"


def test_lote_inexistente_404() -> None:
    r = client.post("/extractions", json={
        "desde": "2026-04-01", "hasta": "2026-05-28", "limite": 5, "tamano_lote": 5,
    })
    job_id = r.json()["id"]
    for _ in range(20):
        time.sleep(0.5)
        if client.get(f"/extractions/{job_id}").json()["estado"] == "completed":
            break
    r = client.get(f"/extractions/{job_id}/lotes/999")
    assert r.status_code == 404


def test_delete_extraccion_limpia_disco_y_db() -> None:
    r = client.post("/extractions", json={
        "desde": "2026-04-01", "hasta": "2026-05-28", "limite": 5, "tamano_lote": 5,
    })
    job_id = r.json()["id"]
    for _ in range(20):
        time.sleep(0.5)
        if client.get(f"/extractions/{job_id}").json()["estado"] == "completed":
            break
    r = client.delete(f"/extractions/{job_id}")
    assert r.status_code == 200
    assert r.json()["borrado"] is True
    # Ya no existe
    r = client.get(f"/extractions/{job_id}")
    assert r.status_code == 404


def test_rango_invalido() -> None:
    r = client.post("/extractions", json={"desde": "2026-05-01", "hasta": "2026-04-01"})
    assert r.status_code == 422


def test_job_inexistente() -> None:
    r = client.get("/extractions/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
