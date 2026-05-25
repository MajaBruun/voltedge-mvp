"""
DDD-objekter for VoltEdge Smart Charging domænet.

Kobling til rapporten (afsnit 4.2):
  - ChargingSession  → Aggregate Root  (ejer session_events og billing_lines)
  - EnergyAmount     → Value Object    (kWh uden selvstændig identitet)
  - BillingLine      → Value Object    (beregnet beløb uden selvstændig identitet)
  - SessionStatus    → Enum            (active / completed)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SessionStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"


# ── Value Objects ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EnergyAmount:
    """Value Object: en mængde energi i kWh.  Uforanderlig og uden ID."""
    kwh: float

    def __post_init__(self):
        if self.kwh < 0:
            raise ValueError(f"EnergyAmount kan ikke være negativ: {self.kwh}")


@dataclass(frozen=True)
class BillingLine:
    """Value Object: beregnet fakturalinje for én session."""
    energy_kwh: float
    price_per_kwh: float
    amount: float          # energy_kwh × price_per_kwh


# ── Aggregate Root ───────────────────────────────────────────────────────────

@dataclass
class ChargingSession:
    """
    Aggregate Root — al interaktion med en ladesession sker GENNEM denne entitet.

    Kobling til rapporten (afsnit 4.2):
      'ChargingSession fungerer som aggregate root, hvilket betyder at al
       interaktion med sessionen — herunder start, stop og statusopdatering
       — sker gennem denne entitet.'
    """
    session_id: str
    charger_id: str
    customer_id: str
    started_at: datetime
    status: SessionStatus = SessionStatus.ACTIVE
    energy_kwh: float = 0.0
    ended_at: Optional[datetime] = None
    load_signal: Optional[str] = None   # BOOST / NORMAL / REDUCE
    billing_line: Optional[BillingLine] = None
    events: list = field(default_factory=list)  # domain events akkumuleres her

    def complete(self, energy_kwh: float, price_per_kwh: float, load_signal: str) -> "ChargingSession":
        """Afslut sessionen og beregn billing. Returnerer self for chaining."""
        energy = EnergyAmount(kwh=energy_kwh)
        amount = round(energy.kwh * price_per_kwh, 2)

        self.energy_kwh = energy.kwh
        self.ended_at = datetime.utcnow()
        self.status = SessionStatus.COMPLETED
        self.load_signal = load_signal
        self.billing_line = BillingLine(
            energy_kwh=energy.kwh,
            price_per_kwh=price_per_kwh,
            amount=amount,
        )
        self.events.append({
            "event_type": "SessionCompleted",
            "session_id": self.session_id,
            "energy_kwh": energy.kwh,
            "amount": amount,
            "load_signal": load_signal,
            "timestamp": self.ended_at.isoformat(),
        })
        return self
