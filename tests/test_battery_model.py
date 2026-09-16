"""
test_battery_model.py -- Tests du simulateur physique (courbes OCV, coulomb counting,
degradation SOH, equilibrage passif, changement de chimie).

Aucune dependance a Qt : ce module ne teste que la physique/logique pure.
"""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from battery_model import (
    Cell, LiveSimulator, CHEMISTRIES, ocv, NUM_CELLS, CAPACITY_NOMINAL_AH,
)


# --------------------------------------------------------------------------- OCV
class TestOCV:
    def test_ocv_at_soc_zero_matches_first_point(self):
        for chem in CHEMISTRIES.values():
            assert ocv(0.0, chem["soc_pts"], chem["ocv_pts"]) == pytest.approx(chem["ocv_pts"][0])

    def test_ocv_at_soc_one_matches_last_point(self):
        for chem in CHEMISTRIES.values():
            assert ocv(1.0, chem["soc_pts"], chem["ocv_pts"]) == pytest.approx(chem["ocv_pts"][-1])

    def test_ocv_clamps_out_of_range_soc(self):
        chem = CHEMISTRIES["liion"]
        assert ocv(-0.5, chem["soc_pts"], chem["ocv_pts"]) == pytest.approx(chem["ocv_pts"][0])
        assert ocv(1.5, chem["soc_pts"], chem["ocv_pts"]) == pytest.approx(chem["ocv_pts"][-1])

    def test_ocv_is_monotonic_non_decreasing(self):
        """Une courbe OCV physique ne doit jamais redescendre quand le SOC augmente."""
        for name, chem in CHEMISTRIES.items():
            samples = [ocv(s / 100, chem["soc_pts"], chem["ocv_pts"]) for s in range(0, 101, 5)]
            for a, b in zip(samples, samples[1:]):
                assert b >= a - 1e-9, f"OCV non-monotone pour la chimie {name}"

    def test_lifepo4_has_flatter_plateau_than_liion(self):
        """Caracteristique connue du LiFePO4 : plateau de tension tres plat au milieu
        de la plage de SOC, contrairement au Li-ion qui monte plus regulierement."""
        lifepo4 = CHEMISTRIES["lifepo4"]
        liion = CHEMISTRIES["liion"]
        lifepo4_mid_spread = ocv(0.8, lifepo4["soc_pts"], lifepo4["ocv_pts"]) - ocv(0.2, lifepo4["soc_pts"], lifepo4["ocv_pts"])
        liion_mid_spread = ocv(0.8, liion["soc_pts"], liion["ocv_pts"]) - ocv(0.2, liion["soc_pts"], liion["ocv_pts"])
        assert lifepo4_mid_spread < liion_mid_spread


# -------------------------------------------------------------------------- Cell
class TestCell:
    def test_discharge_reduces_soc(self):
        cell = Cell(CAPACITY_NOMINAL_AH, r0=0.012, soc=0.5)
        cell.step(current_a=5.0, dt_s=1.0)
        assert cell.soc < 0.5

    def test_charge_increases_soc(self):
        cell = Cell(CAPACITY_NOMINAL_AH, r0=0.012, soc=0.5)
        cell.step(current_a=-5.0, dt_s=1.0)
        assert cell.soc > 0.5

    def test_soc_stays_within_bounds(self):
        cell = Cell(CAPACITY_NOMINAL_AH, r0=0.012, soc=0.02)
        for _ in range(500):
            cell.step(current_a=10.0, dt_s=1.0)
        assert 0.0 <= cell.soc <= 1.0

    def test_terminal_voltage_drops_under_discharge_load(self):
        """La tension aux bornes doit etre inferieure a l'OCV a vide a cause de R0."""
        cell = Cell(CAPACITY_NOMINAL_AH, r0=0.012, soc=0.5)
        ocv_at_rest = ocv(cell.soc)
        v_under_load = cell.step(current_a=10.0, dt_s=1.0)
        assert v_under_load < ocv_at_rest


# ------------------------------------------------------------------ LiveSimulator
class TestLiveSimulator:
    def test_step_returns_expected_keys(self):
        sim = LiveSimulator()
        reading = sim.step()
        for key in ("cell_v", "current_a", "temp_c", "balancing_indices", "soh"):
            assert key in reading

    def test_returns_correct_number_of_cells(self):
        sim = LiveSimulator()
        reading = sim.step()
        assert len(reading["cell_v"]) == NUM_CELLS

    def test_chemistry_switch_updates_voltage_range(self):
        sim = LiveSimulator(chemistry="liion")
        assert sim.v_min == CHEMISTRIES["liion"]["v_min"]
        sim.set_chemistry("lifepo4")
        assert sim.v_min == CHEMISTRIES["lifepo4"]["v_min"]
        assert sim.v_max == CHEMISTRIES["lifepo4"]["v_max"]

    def test_chemistry_switch_updates_cell_curves(self):
        sim = LiveSimulator(chemistry="liion")
        sim.set_chemistry("sodium")
        for cell in sim.cells:
            assert cell.ocv_pts == CHEMISTRIES["sodium"]["ocv_pts"]

    def test_soh_starts_at_100(self):
        sim = LiveSimulator()
        assert sim.soh == pytest.approx(100.0)

    def test_soh_degrades_over_time(self):
        sim = LiveSimulator()
        for _ in range(50):
            sim.step()
        assert sim.soh < 100.0

    def test_soh_never_negative(self):
        sim = LiveSimulator()
        sim.soh = 0.001
        for _ in range(20):
            sim.step()
        assert sim.soh >= 0.0

    def test_fault_scenario_accelerates_soh_degradation(self):
        """Regression du comportement valide manuellement pendant le developpement :
        un scenario de defaut (emballement thermique) doit degrader le SOH plus vite
        qu'un fonctionnement normal, sur le meme nombre de ticks."""
        sim_normal = LiveSimulator()
        sim_normal.set_scenario("normal")
        for _ in range(40):
            sim_normal.step()

        sim_fault = LiveSimulator()
        sim_fault.set_scenario("emballement")
        for _ in range(40):
            sim_fault.step()

        normal_loss = 100.0 - sim_normal.soh
        fault_loss = 100.0 - sim_fault.soh
        assert fault_loss > normal_loss

    def test_autobalance_reduces_overvoltage_cell_towards_average(self):
        sim = LiveSimulator(chemistry="liion")
        sim.set_autobalance(True)
        sim.set_balance_params(turn_on=4.0, precision=0.02)
        # Force artificiellement une cellule haute
        sim.cells[0].soc = 0.99
        for c in sim.cells[1:]:
            c.soc = 0.75

        reading = sim.step()
        # La cellule 0 doit avoir ete identifiee comme en equilibrage au moins une fois
        # sur plusieurs ticks (le seuil peut ne pas etre franchi des le tick 1)
        balancing_ever = False
        for _ in range(20):
            reading = sim.step()
            if 0 in reading["balancing_indices"]:
                balancing_ever = True
                break
        assert balancing_ever

    def test_autobalance_disabled_never_balances(self):
        sim = LiveSimulator(chemistry="liion")
        sim.set_autobalance(False)
        sim.cells[0].soc = 0.99
        for c in sim.cells[1:]:
            c.soc = 0.75
        for _ in range(20):
            reading = sim.step()
            assert reading["balancing_indices"] == []

    def test_weak_cell_is_never_balanced_up(self):
        """Detail physique important : le balancing passif ne peut pas 'recharger'
        une cellule faible, seulement saigner les cellules hautes."""
        sim = LiveSimulator(chemistry="liion")
        sim.set_autobalance(True)
        sim.cells[0].soc = 0.40  # cellule faible
        for c in sim.cells[1:]:
            c.soc = 0.75
        for _ in range(10):
            reading = sim.step()
            assert 0 not in reading["balancing_indices"]
