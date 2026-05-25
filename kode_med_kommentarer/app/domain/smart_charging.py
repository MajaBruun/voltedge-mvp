"""
FIL: app/domain/smart_charging.py
FORMÅL: Smart Charging Domain Service — hjertet i VoltEdges differentiering.

Dette er den fil du bruger mest tid på at forklare til eksamen.
Når du præsenterer: "Her er vores Smart Charging-logik. Den er adskilt fra
resten af koden fordi det er ren forretningslogik — præcis som beskrevet i
rapporten under Domain Service."
"""

from datetime import datetime


# ── Konfiguration: hvornår er det peak-tid? ─────────────────────────────────
# Vi definerer peak-timer én gang øverst i filen.
# Fordelen: hvis VoltEdge vil ændre peak-tiderne, er der kun ét sted at rette.
#
# frozenset er en uforanderlig samling af tal — ligesom en liste, men hurtigere at søge i.
# range(7, 10) giver tallene 7, 8, 9 (ikke 10) — dvs. kl. 07, 08, 09.
PEAK_HOURS = frozenset(range(7, 10)) | frozenset(range(17, 20))   # Morgen: 07-09, Aften: 17-19

# Grænseværdi: over 20 kWh på peak-tid = høj belastning → reducer effekten
HIGH_LOAD_THRESHOLD_KWH = 20.0


# ── Domain Service: beregn styresignal ──────────────────────────────────────
# Dette er vores Domain Service fra rapporten (afsnit 4.2 og 8).
# En Domain Service er en funktion der implementerer forretningslogik som
# involverer flere faktorer og ikke naturligt hører til ét bestemt objekt.
#
# Når du præsenterer: "Her er de tre cases fra rapporten implementeret direkte i kode."

def calculate_load_signal(energy_kwh: float, at: datetime | None = None) -> str:
    """
    Beregner et styresignal baseret på tidspunkt og energiforbrug.

    Returnerer én af tre værdier:
      'REDUCE' → bed ladestanderen om at skrue ned (peak + højt forbrug)
      'NORMAL' → ingen regulering nødvendig (peak + lavt forbrug)
      'BOOST'  → udnyt ledig kapacitet og lad hurtigere (off-peak)

    Eksempel:
      Kl. 08:00, 25 kWh → REDUCE  (travl morgen, højt forbrug)
      Kl. 08:00, 15 kWh → NORMAL  (travl morgen, men lavt forbrug)
      Kl. 14:00, 50 kWh → BOOST   (rolig eftermiddag, ledig kapacitet)
    """
    # Brug det angivne tidspunkt — eller "nu" hvis intet er angivet.
    # 'at' parameteren bruges primært i tests, så vi kan simulere fx kl. 08:00.
    now = at or datetime.utcnow()

    # Udtrækker kun timen fra tidspunktet (0-23)
    hour = now.hour

    # Er vi i peak-tid? (True/False)
    is_peak = hour in PEAK_HOURS

    # ── De tre beslutningsregler fra rapporten ───────────────────────────────

    # Regel 1: Peak-tid OG højt forbrug → reducer effekten for at beskytte nettet
    if is_peak and energy_kwh > HIGH_LOAD_THRESHOLD_KWH:
        return "REDUCE"

    # Regel 2: Peak-tid men lavt forbrug → ingen regulering nødvendig
    if is_peak:
        return "NORMAL"

    # Regel 3: Ikke peak-tid → udnyt den ledige kapacitet fuldt ud
    return "BOOST"
