"""
FIL: tests/test_api.py
FORMÅL: API-tests — tester at alle endpoints opfører sig korrekt udefra.

Disse tests simulerer en rigtig klient der kalder vores API.
De tjekker at vi får de rigtige HTTP-statuskoder og det rigtige indhold tilbage.

Når du præsenterer: "Disse tests tester API'et som en ekstern bruger ville gøre det.
Vi tjekker ikke kun at det virker, men også at fejl håndteres korrekt."
"""

import os
import tempfile
import pytest

# Vi opretter en midlertidig testdatabase-fil FØR vi importerer appen.
# Vi bruger en rigtig fil (ikke :memory:) fordi SQLite in-memory databaser
# kun lever inden for én forbindelse — API-tests ville fejle med "no such table".
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DB_PATH"] = _tmp.name      # Sæt stien til testdatabasen
os.environ["PRICE_PER_KWH"] = "2.50"  # Fast pris så vi kan beregne forventet beløb

# Importer EFTER at vi har sat miljøvariabler — appen læser dem ved import
from fastapi.testclient import TestClient
from app.main import app, startup

# Opret databasetabeller i testdatabasen
startup()

# TestClient er en "falsk browser" der kan kalde vores API uden at starte en server
client = TestClient(app)


# ── Test 1: Health check ─────────────────────────────────────────────────────
def test_health_returnerer_ok():
    """
    /health skal altid returnere {"status": "ok"}.
    Dette er det første vi tjekker — hvis dette fejler, er der noget grundlæggende galt.
    """
    r = client.get("/health")
    assert r.status_code == 200          # 200 = "OK" i HTTP
    assert r.json()["status"] == "ok"


# ── Test 2: Start session ────────────────────────────────────────────────────
def test_start_session_returnerer_201():
    """
    POST /sessions skal returnere 201 (Created) og en aktiv session.
    201 er HTTP-koden for "ressource oprettet" — mere præcis end 200.
    """
    r = client.post("/sessions", json={"charger_id": "CHR-01", "customer_id": "CUST-01"})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "active"    # Ny session starter altid som 'active'
    assert "session_id" in body          # Vi skal have et ID tilbage


# ── Test 3: Komplet flow med billing ────────────────────────────────────────
def test_komplet_session_beregner_billing_korrekt():
    """
    Start en session, afslut den med 10 kWh, tjek at billing er korrekt.
    10 kWh × 2,50 kr/kWh = 25,00 kr — det er hvad vi forventer.

    Dette er den vigtigste test: den tester hele flowet fra start til slut.
    """
    # Trin 1: Start sessionen
    r = client.post("/sessions", json={"charger_id": "CHR-02", "customer_id": "CUST-02"})
    session_id = r.json()["session_id"]  # Gem ID til næste kald

    # Trin 2: Afslut sessionen med 10 kWh
    r = client.post(f"/sessions/{session_id}/complete", json={"energy_kwh": 10.0})
    assert r.status_code == 200
    body = r.json()

    # Tjek at alle felter er korrekte
    assert body["status"] == "completed"
    assert body["energy_kwh"] == 10.0
    assert body["amount"] == pytest.approx(25.0, rel=1e-3)  # pytest.approx håndterer afrundingsfejl
    assert body["load_signal"] in ("BOOST", "NORMAL", "REDUCE")  # Skal være én af de tre


# ── Test 4: Fejlhåndtering — session ikke fundet ────────────────────────────
def test_afslut_ikke_eksisterende_session_returnerer_404():
    """
    Forsøg på at afslutte en session der ikke findes → 404 Not Found.
    404 er HTTP-koden for "ressource ikke fundet".
    """
    r = client.post("/sessions/findes-ikke/complete", json={"energy_kwh": 5.0})
    assert r.status_code == 404


# ── Test 5: Fejlhåndtering — duplikat afslutning ────────────────────────────
def test_afslut_allerede_afsluttet_session_returnerer_409():
    """
    Forsøg på at afslutte en session der allerede er afsluttet → 409 Conflict.
    409 er HTTP-koden for "konflikt" — tilstanden er forkert for denne operation.

    Dette sikrer at vi ikke kan fakturere den samme session to gange.
    """
    # Start og afslut sessionen første gang
    r = client.post("/sessions", json={"charger_id": "CHR-03", "customer_id": "CUST-03"})
    session_id = r.json()["session_id"]
    client.post(f"/sessions/{session_id}/complete", json={"energy_kwh": 5.0})

    # Forsøg at afslutte igen — skal returnere 409
    r = client.post(f"/sessions/{session_id}/complete", json={"energy_kwh": 5.0})
    assert r.status_code == 409


# ── Test 6: Hent session ─────────────────────────────────────────────────────
def test_hent_session_returnerer_korrekt_data():
    """
    GET /sessions/{id} skal returnere den rigtige session.
    Vi tjekker at charger_id matcher det vi sendte ind.
    """
    r = client.post("/sessions", json={"charger_id": "CHR-04", "customer_id": "CUST-04"})
    session_id = r.json()["session_id"]

    r = client.get(f"/sessions/{session_id}")
    assert r.status_code == 200
    assert r.json()["charger_id"] == "CHR-04"  # Data skal matche det vi sendte


# ── Test 7: Analytics ────────────────────────────────────────────────────────
def test_analytics_returnerer_aggregerede_data():
    """
    GET /analytics/summary skal returnere et overblik med de rigtige nøgler.
    Vi tjekker ikke de præcise tal, kun at strukturen er korrekt.
    """
    r = client.get("/analytics/summary")
    assert r.status_code == 200
    body = r.json()
    # Tjek at alle forventede felter er til stede
    assert "completed_sessions" in body
    assert "total_energy_kwh" in body
    assert "total_revenue_dkk" in body
    assert "load_signal_distribution" in body
