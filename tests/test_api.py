"""
API-tests (rapportens afsnit 5.1):
  'API-tests verificerer at platformens endpoints opfører sig korrekt fra et
   eksternt perspektiv — at en POST /sessions returnerer det forventede svar,
   at fejlbehæftede requests håndteres med korrekte HTTP-statuskoder.'

Bruger in-memory SQLite (DB_PATH=:memory:) så tests aldrig rammer produktionsdata.
"""

import os
import pytest

# Sæt test-database FØR app importeres (env-variabel læses ved import)
os.environ["DB_PATH"] = ":memory:"
os.environ["PRICE_PER_KWH"] = "2.50"

from fastapi.testclient import TestClient
from app.main import app, startup

# Kald startup manuelt (TestClient kører ikke lifespan events i alle versioner)
startup()

client = TestClient(app)


def test_health_returns_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_start_session_returns_201():
    r = client.post("/sessions", json={"charger_id": "CHR-01", "customer_id": "CUST-01"})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "active"
    assert "session_id" in body


def test_complete_session_calculates_billing():
    # Start
    r = client.post("/sessions", json={"charger_id": "CHR-02", "customer_id": "CUST-02"})
    session_id = r.json()["session_id"]

    # Afslut med 10 kWh
    r = client.post(f"/sessions/{session_id}/complete", json={"energy_kwh": 10.0})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["energy_kwh"] == 10.0
    assert body["amount"] == pytest.approx(25.0, rel=1e-3)   # 10 × 2.50
    assert body["load_signal"] in ("BOOST", "NORMAL", "REDUCE")


def test_complete_nonexistent_session_returns_404():
    r = client.post("/sessions/does-not-exist/complete", json={"energy_kwh": 5.0})
    assert r.status_code == 404


def test_complete_already_completed_session_returns_409():
    r = client.post("/sessions", json={"charger_id": "CHR-03", "customer_id": "CUST-03"})
    session_id = r.json()["session_id"]
    client.post(f"/sessions/{session_id}/complete", json={"energy_kwh": 5.0})

    # Anden afslutning → 409 Conflict
    r = client.post(f"/sessions/{session_id}/complete", json={"energy_kwh": 5.0})
    assert r.status_code == 409


def test_get_session_returns_correct_data():
    r = client.post("/sessions", json={"charger_id": "CHR-04", "customer_id": "CUST-04"})
    session_id = r.json()["session_id"]
    r = client.get(f"/sessions/{session_id}")
    assert r.status_code == 200
    assert r.json()["charger_id"] == "CHR-04"


def test_analytics_summary_returns_aggregated_data():
    r = client.get("/analytics/summary")
    assert r.status_code == 200
    body = r.json()
    assert "completed_sessions" in body
    assert "total_energy_kwh" in body
    assert "total_revenue_dkk" in body
    assert "load_signal_distribution" in body
