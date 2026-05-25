"""
Smart Charging Domain Service — VoltEdge MVP

Kobling til rapporten (afsnit 4.2 + 8):
  'Domain Service — calculate_load_signal() implementerer Smart Charging-logikken
   og placeres som en selvstændig funktion fordi logikken involverer flere faktorer
   og ikke naturligt tilhører én entitet.'

Logik (fra rapportens afsnit 8):
  REDUCE — peak-tidspunkt (07-09 eller 17-19) OG forbrug > 20 kWh
  NORMAL — peak-tidspunkt OG forbrug <= 20 kWh
  BOOST  — off-peak tidspunkt (ledig kapacitet udnyttes)
"""

from datetime import datetime


PEAK_HOURS = frozenset(range(7, 10)) | frozenset(range(17, 20))   # 07-09, 17-19
HIGH_LOAD_THRESHOLD_KWH = 20.0


def calculate_load_signal(energy_kwh: float, at: datetime | None = None) -> str:
    """
    Beregn styresignal for Smart Charging baseret på tidspunkt og energiforbrug.

    Args:
        energy_kwh: Energiforbrug i kWh for den aktuelle session.
        at:         Tidspunkt der evalueres (default: nu / UTC).

    Returns:
        'REDUCE', 'NORMAL' eller 'BOOST'
    """
    now = at or datetime.utcnow()
    hour = now.hour
    is_peak = hour in PEAK_HOURS

    if is_peak and energy_kwh > HIGH_LOAD_THRESHOLD_KWH:
        return "REDUCE"
    if is_peak:
        return "NORMAL"
    return "BOOST"
