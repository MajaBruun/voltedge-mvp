"""
Unit tests for Smart Charging domain service (rapportens afsnit 5.1 + 8).

De tre testcases er direkte fra rapporten:
  'Peak + forbrug over 20 kWh → REDUCE'
  'Peak + forbrug under 20 kWh → NORMAL'
  'Off-peak → BOOST'
  'Aftenpeak + forbrug over 20 kWh → REDUCE'
"""

from datetime import datetime
import pytest

from app.domain.smart_charging import calculate_load_signal


def peak_morning(hour=8):
    """Hjælper: returnerer et datetime-objekt i peak-morgenperioden."""
    return datetime(2024, 6, 1, hour, 0, 0)


def peak_evening(hour=18):
    return datetime(2024, 6, 1, hour, 0, 0)


def off_peak(hour=14):
    return datetime(2024, 6, 1, hour, 0, 0)


class TestSmartChargingDomainService:
    # ── De fire cases fra rapporten ─────────────────────────────────────────

    def test_peak_high_load_returns_reduce(self):
        """Peak-tidspunkt OG forbrug > 20 kWh → REDUCE."""
        signal = calculate_load_signal(energy_kwh=25.0, at=peak_morning())
        assert signal == "REDUCE"

    def test_peak_low_load_returns_normal(self):
        """Peak-tidspunkt OG forbrug <= 20 kWh → NORMAL."""
        signal = calculate_load_signal(energy_kwh=15.0, at=peak_morning())
        assert signal == "NORMAL"

    def test_off_peak_returns_boost(self):
        """Off-peak → BOOST uanset forbrug."""
        signal = calculate_load_signal(energy_kwh=50.0, at=off_peak())
        assert signal == "BOOST"

    def test_evening_peak_high_load_returns_reduce(self):
        """Aftenpeak + forbrug > 20 kWh → REDUCE."""
        signal = calculate_load_signal(energy_kwh=30.0, at=peak_evening())
        assert signal == "REDUCE"

    # ── Grænseværdier ───────────────────────────────────────────────────────

    def test_exactly_20_kwh_at_peak_is_normal(self):
        """Præcis 20 kWh er under tærsklen → NORMAL."""
        signal = calculate_load_signal(energy_kwh=20.0, at=peak_morning())
        assert signal == "NORMAL"

    def test_zero_kwh_off_peak_is_boost(self):
        signal = calculate_load_signal(energy_kwh=0.0, at=off_peak())
        assert signal == "BOOST"

    def test_midnight_is_off_peak(self):
        midnight = datetime(2024, 6, 1, 0, 0, 0)
        signal = calculate_load_signal(energy_kwh=100.0, at=midnight)
        assert signal == "BOOST"
