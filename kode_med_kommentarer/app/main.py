"""
FIL: app/main.py
FORMÅL: Selve API'et — alle endpoints der kan kaldes udefra.

Dette er "indgangsdøren" til hele systemet.
Når du præsenterer: "Her definerer vi vores API. FastAPI giver os automatisk
en interaktiv dokumentationsside på /docs, som vi kan bruge til at
demonstrere systemet live."
"""

import json
import logging
import os
import uuid
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException  # FastAPI er vores API-framework
from pydantic import BaseModel              # Pydantic validerer at requests har korrekt format

# Importer vores egne moduler
from app.database import db, init_db
from app.domain.models import ChargingSession, SessionStatus
from app.domain.smart_charging import calculate_load_signal

# Indlæs værdier fra .env-filen
load_dotenv()

# ── Logning ──────────────────────────────────────────────────────────────────
# Struktureret logning: alle hændelser skrives til konsollen med tidsstempel.
# Format: "2024-06-01 08:00:00 [INFO] voltedge — SessionStarted | session_id=..."
# I produktion ville dette sendes til Azure Monitor.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("voltedge")

# Pris per kWh hentes fra miljøvariabel — ALDRIG hardkodet i koden.
# Standardværdien 2.50 bruges kun hvis variablen ikke er sat.
PRICE_PER_KWH = float(os.getenv("PRICE_PER_KWH", "2.50"))

# ── Opret FastAPI-applikationen ──────────────────────────────────────────────
# title og description vises på /docs-siden
app = FastAPI(
    title="VoltEdge MVP",
    description="Smart Charging platform — MVP demonstrerer afsnit 3-6 fra rapporten.",
    version="1.0.0",
)


# ── Startup: køres automatisk når applikationen starter ─────────────────────
@app.on_event("startup")
def startup():
    """Opretter databasetabeller ved opstart (hvis de ikke allerede findes)."""
    init_db()
    logger.info("Database initialiseret ✓")


# ── Datamodeller (schemas) ───────────────────────────────────────────────────
# Pydantic-modeller definerer hvad API'et forventer at modtage og sende.
# Pydantic validerer automatisk at inputs har korrekt type og format.
# Når du præsenterer: "Disse klasser sikrer at vi ikke kan sende forkerte data ind."

class StartSessionRequest(BaseModel):
    """Det vi forventer at modtage når en ladestander starter en session."""
    charger_id: str      # Fx "CHR-01"
    customer_id: str     # Fx "CUST-42"


class CompleteSessionRequest(BaseModel):
    """Det vi forventer at modtage når en session afsluttes."""
    energy_kwh: float    # Fx 25.0


class SessionResponse(BaseModel):
    """Det vi sender tilbage som svar — samme format hver gang."""
    session_id: str
    charger_id: str
    customer_id: str
    status: str
    started_at: str
    ended_at: str | None = None        # Tomt hvis sessionen stadig er aktiv
    energy_kwh: float | None = None    # Tomt hvis sessionen stadig er aktiv
    amount: float | None = None        # Tomt hvis sessionen stadig er aktiv
    load_signal: str | None = None     # Tomt hvis sessionen stadig er aktiv


# ── Endpoints (routes) ───────────────────────────────────────────────────────

@app.post("/sessions", response_model=SessionResponse, status_code=201)
def start_session(body: StartSessionRequest):
    """
    START en ny ladesession.

    HTTP POST til /sessions med charger_id og customer_id.
    Returnerer en ny session med status='active' og et unikt session_id.

    Hvad sker der bag kulisserne:
      1. Generer et unikt ID (UUID)
      2. Gem sessionen i databasen med status='active'
      3. Log et 'SessionStarted' domain event i audit loggen
      4. Returner session-data til klienten
    """
    # uuid.uuid4() genererer et globalt unikt ID — fx "a3f9c2b1-..."
    # Det er ekstremt usandsynligt at to sessioner får samme ID
    session_id = str(uuid.uuid4())
    started_at = datetime.utcnow().isoformat()

    # Gem i databasen
    with db() as conn:
        # Indsæt ny session-række
        conn.execute(
            """INSERT INTO charging_sessions
               (session_id, charger_id, customer_id, started_at, status)
               VALUES (?, ?, ?, ?, 'active')""",
            (session_id, body.charger_id, body.customer_id, started_at),
        )
        # Log domain event i audit loggen
        # json.dumps() konverterer Python-dict til JSON-tekst til lagring
        conn.execute(
            """INSERT INTO session_events (session_id, event_type, payload)
               VALUES (?, 'SessionStarted', ?)""",
            (session_id, json.dumps({"charger_id": body.charger_id, "customer_id": body.customer_id})),
        )

    # Log til konsollen så vi kan se hvad der sker i realtid
    logger.info("SessionStarted | session_id=%s charger=%s customer=%s",
                session_id, body.charger_id, body.customer_id)

    return SessionResponse(
        session_id=session_id,
        charger_id=body.charger_id,
        customer_id=body.customer_id,
        status="active",
        started_at=started_at,
    )


@app.post("/sessions/{session_id}/complete", response_model=SessionResponse)
def complete_session(session_id: str, body: CompleteSessionRequest):
    """
    AFSLUT en ladesession + kør Smart Charging + beregn billing.

    HTTP POST til /sessions/{id}/complete med energy_kwh.

    Dette endpoint er det vigtigste i systemet — her sker tre ting:
      1. Smart Charging domain service beregner styresignal (BOOST/NORMAL/REDUCE)
      2. Billing beregnes automatisk (kWh × pris)
      3. SessionCompleted domain event logges i audit loggen

    Fejlhåndtering:
      404 → session findes ikke
      409 → session er allerede afsluttet (duplikat-beskyttelse)
    """
    with db() as conn:
        # Slå sessionen op i databasen
        row = conn.execute(
            "SELECT * FROM charging_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()

        # Fejl 404: Session ikke fundet
        if not row:
            raise HTTPException(status_code=404, detail="Session ikke fundet")

        # Fejl 409: Session er allerede afsluttet — vi kan ikke afslutte den igen
        if row["status"] == "completed":
            raise HTTPException(status_code=409, detail="Session er allerede afsluttet")

        # ── Kald Smart Charging Domain Service ───────────────────────────────
        # calculate_load_signal() er vores domain service fra smart_charging.py
        # Den returnerer 'REDUCE', 'NORMAL' eller 'BOOST'
        load_signal = calculate_load_signal(body.energy_kwh)

        # ── Beregn billing automatisk ─────────────────────────────────────────
        # round(..., 2) sikrer præcis øre-beregning (fx 62.50 kr, ikke 62.500000001)
        amount = round(body.energy_kwh * PRICE_PER_KWH, 2)
        ended_at = datetime.utcnow().isoformat()

        # Opdater sessionen i databasen
        conn.execute(
            """UPDATE charging_sessions
               SET status='completed', energy_kwh=?, amount=?, load_signal=?, ended_at=?
               WHERE session_id=?""",
            (body.energy_kwh, amount, load_signal, ended_at, session_id),
        )

        # Log SessionCompleted domain event i audit loggen
        conn.execute(
            """INSERT INTO session_events (session_id, event_type, payload)
               VALUES (?, 'SessionCompleted', ?)""",
            (session_id, json.dumps({
                "energy_kwh": body.energy_kwh,
                "amount": amount,
                "load_signal": load_signal,
            })),
        )

    # Log til konsollen med alle relevante detaljer
    logger.info(
        "SessionCompleted | session_id=%s energy=%.2f kWh amount=%.2f kr load_signal=%s",
        session_id, body.energy_kwh, amount, load_signal,
    )

    return SessionResponse(
        session_id=session_id,
        charger_id=row["charger_id"],
        customer_id=row["customer_id"],
        status="completed",
        started_at=row["started_at"],
        ended_at=ended_at,
        energy_kwh=body.energy_kwh,
        amount=amount,
        load_signal=load_signal,
    )


@app.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str):
    """
    HENT status på én specifik session.

    HTTP GET til /sessions/{id}.
    Returnerer 404 hvis sessionen ikke findes.
    """
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM charging_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session ikke fundet")
    # dict(row) konverterer databaserækken til et Python-dictionary
    return SessionResponse(**dict(row))


@app.get("/analytics/summary")
def analytics_summary():
    """
    DESKRIPTIV ANALYSE — overblik over alle afsluttede sessioner.

    HTTP GET til /analytics/summary.
    Returnerer aggregerede nøgletal fra databasen:
      - Antal afsluttede sessioner
      - Total energileverance i kWh
      - Total omsætning i kr.
      - Fordeling på load_signal (hvor mange BOOST, NORMAL, REDUCE)

    Når du præsenterer: "Dette svarer til det deskriptive analyse-lag
    fra rapporten afsnit 6.3 — vi besvarer spørgsmålet 'hvad er sket?'"
    """
    with db() as conn:
        # Tæl antal afsluttede sessioner
        total = conn.execute(
            "SELECT COUNT(*) as n FROM charging_sessions WHERE status='completed'"
        ).fetchone()["n"]

        # Summer energi og omsætning
        # COALESCE(SUM(...), 0) returnerer 0 hvis der ingen sessioner er (undgår NULL)
        energy_row = conn.execute(
            "SELECT COALESCE(SUM(energy_kwh),0) as e, COALESCE(SUM(amount),0) as a "
            "FROM charging_sessions WHERE status='completed'"
        ).fetchone()

        # Tæl fordeling på load_signal (GROUP BY = gruppér efter)
        signal_rows = conn.execute(
            "SELECT load_signal, COUNT(*) as n FROM charging_sessions "
            "WHERE status='completed' GROUP BY load_signal"
        ).fetchall()

    # Lav en dictionary: {"BOOST": 5, "NORMAL": 3, "REDUCE": 2}
    signal_dist = {r["load_signal"]: r["n"] for r in signal_rows}

    return {
        "completed_sessions": total,
        "total_energy_kwh": round(energy_row["e"], 2),
        "total_revenue_dkk": round(energy_row["a"], 2),
        "load_signal_distribution": signal_dist,
        "price_per_kwh": PRICE_PER_KWH,
    }


@app.get("/health")
def health():
    """
    HEALTH CHECK — bruges til driftsovervågning.

    HTTP GET til /health.
    Returnerer simpelt svar: {"status": "ok"}.

    I produktion kalder Azure App Service dette endpoint hvert 30. sekund.
    Hvis svaret udebliver, registreres det som nedetid og en alarm udløses.
    Når du præsenterer: "Dette er vores driftsovervågning i praksis."
    """
    return {"status": "ok", "service": "voltedge-mvp"}
