"""
FIL: tests/test_smart_charging.py
FORMÅL: Unit tests for Smart Charging domain servicen.

Unit tests tester én funktion isoleret — uden database, uden API, uden netværk.
De er hurtige at køre og fanger fejl tidligt.

Når du præsenterer: "Her tester vi at vores Smart Charging-logik opfører sig
korrekt. De fire første tests er direkte taget fra rapporten."
"""

from datetime import datetime
import pytest

# Importer kun den funktion vi vil teste
from app.domain.smart_charging import calculate_load_signal


# ── Hjælpefunktioner til at simulere tidspunkter ────────────────────────────
# Vi laver falske tidspunkter så vi kan teste alle tre cases uanset
# hvad klokken er i virkeligheden, når testen kører.

def peak_morgen(hour=8):
    """Simulerer kl. 08:00 — midt i morgen-peak (07-09)."""
    return datetime(2024, 6, 1, hour, 0, 0)

def peak_aften(hour=18):
    """Simulerer kl. 18:00 — midt i aften-peak (17-19)."""
    return datetime(2024, 6, 1, hour, 0, 0)

def off_peak(hour=14):
    """Simulerer kl. 14:00 — rolig eftermiddag uden peak."""
    return datetime(2024, 6, 1, hour, 0, 0)


# ── Testklasse med alle tests ────────────────────────────────────────────────
# Vi samler tests i en klasse for at holde dem organiserede.
# pytest finder automatisk alle metoder der starter med 'test_'.

class TestSmartChargingDomainService:

    # ── De fire cases direkte fra rapporten (afsnit 8) ──────────────────────

    def test_peak_hoejt_forbrug_returnerer_reduce(self):
        """
        Peak-tidspunkt OG forbrug > 20 kWh → REDUCE.
        Systemet skal bede ladestanderen om at skrue ned for at beskytte nettet.
        """
        signal = calculate_load_signal(energy_kwh=25.0, at=peak_morgen())
        assert signal == "REDUCE"  # 'assert' fejler testen hvis betingelsen ikke er opfyldt

    def test_peak_lavt_forbrug_returnerer_normal(self):
        """
        Peak-tidspunkt OG forbrug <= 20 kWh → NORMAL.
        Forbruget er lavt nok til at ingen regulering er nødvendig.
        """
        signal = calculate_load_signal(energy_kwh=15.0, at=peak_morgen())
        assert signal == "NORMAL"

    def test_off_peak_returnerer_boost(self):
        """
        Off-peak tidspunkt → BOOST uanset forbruget.
        Der er ledig kapacitet, så vi udnytter den fuldt ud.
        """
        signal = calculate_load_signal(energy_kwh=50.0, at=off_peak())
        assert signal == "BOOST"

    def test_aftenpeak_hoejt_forbrug_returnerer_reduce(self):
        """
        Aften-peak (17-19) OG forbrug > 20 kWh → REDUCE.
        Samme logik som morgen-peak, men om aftenen.
        """
        signal = calculate_load_signal(energy_kwh=30.0, at=peak_aften())
        assert signal == "REDUCE"

    # ── Grænseværdi-tests ────────────────────────────────────────────────────
    # Grænseværdier er de "kanttilfælde" der oftest skjuler fejl i kode.
    # Vi tester præcis 20 kWh — er det over eller under grænsen?

    def test_praecis_20_kwh_paa_peak_er_normal(self):
        """
        Præcis 20 kWh er IKKE over tærsklen (> 20) → NORMAL.
        Tester at vi bruger '>' og ikke '>=' i logikken.
        """
        signal = calculate_load_signal(energy_kwh=20.0, at=peak_morgen())
        assert signal == "NORMAL"

    def test_nul_kwh_off_peak_er_boost(self):
        """
        0 kWh off-peak → BOOST. Systemet skal kunne håndtere tomme sessioner.
        """
        signal = calculate_load_signal(energy_kwh=0.0, at=off_peak())
        assert signal == "BOOST"

    def test_midnat_er_off_peak(self):
        """
        Kl. 00:00 (midnat) → BOOST. Midnat er ikke peak-tid.
        Tester at vi ikke ved en fejl har defineret midnat som peak.
        """
        midnat = datetime(2024, 6, 1, 0, 0, 0)
        signal = calculate_load_signal(energy_kwh=100.0, at=midnat)
        assert signal == "BOOST"
