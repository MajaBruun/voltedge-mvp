"""
VoltEdge MVP — FastAPI application

Endpoints:
  POST   /sessions               → Start en ny ladesession (SessionStarted event)
  POST   /sessions/{id}/complete → Afslut session + kør Smart Charging + billing
  GET    /sessions/{id}          → Hent status på én session
  GET    /analytics/summary      → Deskriptiv analyse (afsnit 6.3)
  GET    /health                 → Driftsstatus (afsnit 5.4)
"""

import json
import logging
import os
import uuid
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.database import db, init_db
from app.domain.models import ChargingSession, SessionStatus
from app.domain.smart_charging import calculate_load_signal

load_dotenv()

# ── Logging (afsnit 5.4: struktureret logning med tidsstempel og kontekst) ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("voltedge")

PRICE_PER_KWH = float(os.getenv("PRICE_PER_KWH", "2.50"))

app = FastAPI(
    title="VoltEdge MVP",
    description="Smart Charging platform — MVP demonstrerer afsnit 3-6 fra rapporten.",
    version="1.0.0",
)


@app.on_event("startup")
def startup():
    init_db()
    logger.info("Database initialiseret ✓")


# ── Pydantic-schemas (request / response) ───────────────────────────────────

class StartSessionRequest(BaseModel):
    charger_id: str
    customer_id: str


class CompleteSessionRequest(BaseModel):
    energy_kwh: float


class SessionResponse(BaseModel):
    session_id: str
    charger_id: str
    customer_id: str
    status: str
    started_at: str
    ended_at: str | None = None
    energy_kwh: float | None = None
    amount: float | None = None
    load_signal: str | None = None


# ── Routes ───────────────────────────────────────────────────────────────────

@app.post("/sessions", response_model=SessionResponse, status_code=201)
def start_session(body: StartSessionRequest):
    """
    Start en ny ladesession.
    Domain event 'SessionStarted' logges i session_events.
    """
    session_id = str(uuid.uuid4())
    started_at = datetime.utcnow().isoformat()

    with db() as conn:
        conn.execute(
            """INSERT INTO charging_sessions
               (session_id, charger_id, customer_id, started_at, status)
               VALUES (?, ?, ?, ?, 'active')""",
            (session_id, body.charger_id, body.customer_id, started_at),
        )
        conn.execute(
            """INSERT INTO session_events (session_id, event_type, payload)
               VALUES (?, 'SessionStarted', ?)""",
            (session_id, json.dumps({"charger_id": body.charger_id, "customer_id": body.customer_id})),
        )

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
    Afslut session:
      1. Kør Smart Charging domain service → load_signal
      2. Beregn billing (energy × pris)
      3. Persist SessionCompleted domain event
    """
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM charging_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Session ikke fundet")
        if row["status"] == "completed":
            raise HTTPException(status_code=409, detail="Session er allerede afsluttet")

        # Domain service
        load_signal = calculate_load_signal(body.energy_kwh)
        amount = round(body.energy_kwh * PRICE_PER_KWH, 2)
        ended_at = datetime.utcnow().isoformat()

        conn.execute(
            """UPDATE charging_sessions
               SET status='completed', energy_kwh=?, amount=?, load_signal=?, ended_at=?
               WHERE session_id=?""",
            (body.energy_kwh, amount, load_signal, ended_at, session_id),
        )
        conn.execute(
            """INSERT INTO session_events (session_id, event_type, payload)
               VALUES (?, 'SessionCompleted', ?)""",
            (session_id, json.dumps({
                "energy_kwh": body.energy_kwh,
                "amount": amount,
                "load_signal": load_signal,
            })),
        )

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
    """Hent status på én session."""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM charging_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session ikke fundet")
    return SessionResponse(**dict(row))


@app.get("/analytics/summary")
def analytics_summary():
    """
    Deskriptiv analyse (rapportens afsnit 6.3):
      - Antal sessioner i alt
      - Total energileverance (kWh)
      - Total omsætning (kr.)
      - Fordeling på load_signal (BOOST / NORMAL / REDUCE)
    """
    with db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) as n FROM charging_sessions WHERE status='completed'"
        ).fetchone()["n"]

        energy_row = conn.execute(
            "SELECT COALESCE(SUM(energy_kwh),0) as e, COALESCE(SUM(amount),0) as a "
            "FROM charging_sessions WHERE status='completed'"
        ).fetchone()

        signal_rows = conn.execute(
            "SELECT load_signal, COUNT(*) as n FROM charging_sessions "
            "WHERE status='completed' GROUP BY load_signal"
        ).fetchall()

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
    Health-check endpoint (rapportens afsnit 5.4).
    Azure App Service kalder dette endpoint løbende.
    """
    return {"status": "ok", "service": "voltedge-mvp"}
