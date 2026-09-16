"""
test_main_window.py -- Tests d'integration sur la logique de MainWindow qui ne peut
pas etre isolee de Qt (detection d'evenements a front montant, RUL, cycles, PIN).

Utilise le fixture isolated_window (voir conftest.py) : QSettings et history.db
pointent vers un dossier temporaire, jamais la vraie configuration de l'utilisateur.
"""

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestProtectionEventEdgeTriggering:
    """La detection doit compter un evenement par FRANCHISSEMENT de seuil, pas une
    fois par tick tant que la condition reste vraie -- sinon le compteur explose
    en quelques secondes des qu'un defaut est actif."""

    def test_overvoltage_counted_once_while_sustained(self, isolated_window):
        win = isolated_window
        voltages = [4.30] * 10  # tous au-dessus du seuil par defaut (4.20V)
        for _ in range(10):
            win._check_protection_events(voltages, current=1.0, temp=25.0)
        assert win.protection_events["cell_overvoltage"] == 1

    def test_overvoltage_counted_again_after_release_and_retrigger(self, isolated_window):
        win = isolated_window
        high = [4.30] * 10
        low = [3.80] * 10  # repasse sous le seuil de relachement (4.15V)

        win._check_protection_events(high, current=1.0, temp=25.0)
        win._check_protection_events(low, current=1.0, temp=25.0)
        win._check_protection_events(high, current=1.0, temp=25.0)

        assert win.protection_events["cell_overvoltage"] == 2

    def test_no_event_when_within_normal_range(self, isolated_window):
        win = isolated_window
        normal = [3.75] * 10
        for _ in range(10):
            win._check_protection_events(normal, current=1.0, temp=25.0)
        assert sum(win.protection_events.values()) == 0

    def test_charge_and_discharge_overcurrent_are_independent(self, isolated_window):
        win = isolated_window
        voltages = [3.75] * 10
        # Courant negatif = charge ; positif = decharge (convention du simulateur)
        win._check_protection_events(voltages, current=-35.0, temp=25.0)  # surintensite charge
        assert win.protection_events["charge_overcurrent"] == 1
        assert win.protection_events["discharge_overcurrent"] == 0


class TestBatteryCycles:
    def test_cycle_counted_on_full_swing(self, isolated_window):
        win = isolated_window
        win._check_battery_cycles(soc=15)   # arme (sous 20%)
        win._check_battery_cycles(soc=50)   # transitoire, ne doit rien declencher
        win._check_battery_cycles(soc=85)   # valide le cycle (au-dessus de 80%)
        assert win.battery_cycles == 1

    def test_no_cycle_without_low_point_first(self, isolated_window):
        win = isolated_window
        win._check_battery_cycles(soc=85)  # jamais descendu sous 20% -> pas de cycle
        assert win.battery_cycles == 0

    def test_partial_swing_does_not_count(self, isolated_window):
        win = isolated_window
        win._check_battery_cycles(soc=15)
        win._check_battery_cycles(soc=50)  # ne redescend jamais, ne remonte pas a 80
        assert win.battery_cycles == 0


class TestPinProtection:
    def test_default_pin_hash_matches_1234(self, isolated_window):
        win = isolated_window
        assert win.pin_hash == hashlib.sha256(b"1234").hexdigest()

    def test_reset_factory_settings_restores_default_pin(self, isolated_window, monkeypatch):
        win = isolated_window
        win.pin_hash = hashlib.sha256(b"9999").hexdigest()

        # Simule un PIN valide saisi + confirmation "Oui" sans ouvrir de vraie boite de dialogue
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("9999", True)))
        monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
        monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

        win._reset_factory_settings()
        assert win.pin_hash == hashlib.sha256(b"1234").hexdigest()


class TestRulEstimate:
    def test_not_enough_data_shows_collecting_message(self, isolated_window):
        win = isolated_window
        win.soh_history.clear()
        for i in range(3):
            win.soh_history.append((i, 100.0 - i * 0.01))
        win._update_rul_estimate()
        assert "collecte" in win.soh_trend_lbl.text().lower()

    def test_declining_soh_produces_rul_estimate(self, isolated_window):
        win = isolated_window
        win.soh_history.clear()
        for i in range(20):
            win.soh_history.append((i, 100.0 - i * 0.5))  # pente forte et nette
        win._update_rul_estimate()
        assert "RUL" in win.soh_trend_lbl.text()

    def test_stable_soh_reports_stable(self, isolated_window):
        win = isolated_window
        win.soh_history.clear()
        for i in range(20):
            win.soh_history.append((i, 99.0))  # totalement plat
        win._update_rul_estimate()
        assert "stable" in win.soh_trend_lbl.text().lower()


class TestChemistrySwitch:
    def test_set_chemistry_updates_protection_defaults(self, isolated_window):
        win = isolated_window
        win._set_chemistry("lifepo4")
        from battery_model import CHEMISTRIES
        assert win.protection_params["overvoltage"] == CHEMISTRIES["lifepo4"]["default_overvoltage"]
        assert win.sim.chemistry == "lifepo4"

    def test_set_chemistry_updates_cell_bank_range(self, isolated_window):
        win = isolated_window
        win._set_chemistry("sodium")
        from battery_model import CHEMISTRIES
        assert win.cell_bank.v_min == CHEMISTRIES["sodium"]["v_min"]
