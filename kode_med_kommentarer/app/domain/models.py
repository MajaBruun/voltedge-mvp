"""
FIL: app/domain/models.py
FORMÅL: Definerer de centrale forretningsobjekter (DDD-objekter) for VoltEdge.

Når du præsenterer denne fil, kan du sige:
  "Her er vores domænemodel — det er her forretningslogikken bor.
   Vi har tre klasser, og de afspejler direkte det vi beskriver i rapporten."
"""

# Vi henter værktøjer fra Pythons standardbibliotek.
# 'dataclass' gør det nemt at lave dataobjekter uden meget kode.
# 'Enum' bruges til at definere faste valgmuligheder (som en rullemenu).
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ── SessionStatus: en "rullemenu" med to mulige tilstande ───────────────────
# En session kan kun være enten 'active' eller 'completed' — aldrig noget andet.
# Det forhindrer fejl, fordi vi ikke kan komme til at skrive fx "done" ved en fejl.
class SessionStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"


# ── Value Objects ────────────────────────────────────────────────────────────
# Value Objects er simple dataobjekter uden eget ID.
# De bruges til at pakke en værdi ind med validering.
# Når du præsenterer: "EnergyAmount sikrer at vi aldrig kan registrere negativt forbrug."

@dataclass(frozen=True)  # 'frozen=True' betyder at værdien ikke kan ændres efter oprettelse
class EnergyAmount:
    """Repræsenterer en mængde energi i kWh. Kan ikke være negativ."""
    kwh: float

    def __post_init__(self):
        # Denne kode køres automatisk når vi opretter et EnergyAmount-objekt.
        # Hvis nogen prøver at sende -5 kWh, kaster vi en fejl med det samme.
        if self.kwh < 0:
            raise ValueError(f"Energiforbrug kan ikke være negativt: {self.kwh} kWh")


@dataclass(frozen=True)
class BillingLine:
    """Repræsenterer den beregnede fakturalinje for én ladesession."""
    energy_kwh: float       # Hvor mange kWh der er brugt
    price_per_kwh: float    # Pris per kWh (hentes fra .env-filen)
    amount: float           # Det samlede beløb = energy_kwh × price_per_kwh


# ── Aggregate Root ───────────────────────────────────────────────────────────
# ChargingSession er vores vigtigste objekt — det vi kalder "Aggregate Root" i rapporten.
# AL interaktion med en ladesession sker GENNEM denne klasse.
# Det er som en dørmand: alt skal igennem ChargingSession, intet går udenom.
# Når du præsenterer: "Her ser vi Aggregate Root-mønsteret fra rapporten i praksis."

@dataclass
class ChargingSession:
    """
    Aggregate Root for en ladesession.

    Denne klasse ejer al data og logik for én ladesession:
    - Hvem der lader (customer_id)
    - Hvilken ladestander der bruges (charger_id)
    - Hvornår sessionen startede og sluttede
    - Hvor meget energi der er brugt
    - Hvad det koster (BillingLine)
    - Hvilke hændelser der er sket (events)
    """
    session_id: str          # Unikt ID — genereres automatisk (UUID)
    charger_id: str          # ID på ladestanderen, fx "CHR-01"
    customer_id: str         # ID på kunden, fx "CUST-42"
    started_at: datetime     # Tidspunkt for sessionstart

    # Disse felter udfyldes undervejs — de er tomme/None til at starte med
    status: SessionStatus = SessionStatus.ACTIVE   # Starter altid som 'active'
    energy_kwh: float = 0.0                        # Opdateres når sessionen slutter
    ended_at: Optional[datetime] = None            # Sættes når sessionen slutter
    load_signal: Optional[str] = None             # BOOST, NORMAL eller REDUCE
    billing_line: Optional[BillingLine] = None    # Beregnes når sessionen slutter
    events: list = field(default_factory=list)    # Liste over alle hændelser (audit log)

    def complete(self, energy_kwh: float, price_per_kwh: float, load_signal: str) -> "ChargingSession":
        """
        Afslutter sessionen.

        Denne metode gør tre ting på én gang:
          1. Registrerer energiforbruget og beregner prisen
          2. Sætter status til 'completed'
          3. Tilføjer et 'SessionCompleted' domain event til audit loggen

        Når du præsenterer: "Her sker det vigtige — sessionen afsluttes,
        billing beregnes automatisk, og hændelsen logges til audit loggen."
        """
        # Brug EnergyAmount-objektet — det validerer at kWh ikke er negativ
        energy = EnergyAmount(kwh=energy_kwh)

        # Beregn det samlede beløb og afrund til 2 decimaler (øre-præcision)
        amount = round(energy.kwh * price_per_kwh, 2)

        # Opdater alle felter på sessionen
        self.energy_kwh = energy.kwh
        self.ended_at = datetime.utcnow()
        self.status = SessionStatus.COMPLETED
        self.load_signal = load_signal
        self.billing_line = BillingLine(
            energy_kwh=energy.kwh,
            price_per_kwh=price_per_kwh,
            amount=amount,
        )

        # Tilføj et domain event til audit loggen
        # Dette event gemmes i databasen og giver fuld sporbarhed fra session til faktura
        self.events.append({
            "event_type": "SessionCompleted",
            "session_id": self.session_id,
            "energy_kwh": energy.kwh,
            "amount": amount,
            "load_signal": load_signal,
            "timestamp": self.ended_at.isoformat(),
        })

        return self  # Returnerer sig selv så vi kan skrive session.complete(...).status osv.
