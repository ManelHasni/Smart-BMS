"""
test_features.py -- Tests de extract_features() : le pont entre les lectures brutes
du simulateur et le vecteur d'entree du modele Random Forest.

Import de main.py sans QApplication (verifie que le module reste importable pour
des tests rapides, purement logiques -- voir conftest.py pour les tests qui ont
besoin d'une vraie fenetre).
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import extract_features, FEATURE_ORDER
from battery_model import NUM_CELLS


def make_reading(cell_v, current_a, temp_c):
    return {"cell_v": cell_v, "current_a": current_a, "temp_c": temp_c}


@pytest.fixture
def flat_window():
    """Fenetre de 10 lectures identiques -- toutes les cellules a 3.75V, courant
    et temperature constants : le cas le plus simple a verifier a la main."""
    reading = make_reading([3.75] * NUM_CELLS, 5.0, 25.0)
    return [reading.copy() for _ in range(10)]


class TestExtractFeatures:
    def test_returns_all_expected_keys(self, flat_window):
        features = extract_features(flat_window)
        for key in FEATURE_ORDER:
            assert key in features

    def test_flat_window_has_zero_std(self, flat_window):
        """Si toutes les lectures sont identiques, les ecarts-types doivent etre nuls."""
        features = extract_features(flat_window)
        assert features["v_cell_std"] == pytest.approx(0.0, abs=1e-9)
        assert features["current_std"] == pytest.approx(0.0, abs=1e-9)

    def test_flat_window_has_zero_imbalance(self, flat_window):
        features = extract_features(flat_window)
        assert features["v_imbalance"] == pytest.approx(0.0, abs=1e-9)

    def test_flat_window_pack_voltage(self, flat_window):
        features = extract_features(flat_window)
        assert features["pack_v_mean"] == pytest.approx(3.75 * NUM_CELLS)

    def test_flat_window_zero_temp_slope(self, flat_window):
        features = extract_features(flat_window)
        assert features["temp_slope"] == pytest.approx(0.0, abs=1e-9)

    def test_imbalanced_window_detects_spread(self):
        cell_v = [3.75] * NUM_CELLS
        cell_v[3] = 3.40  # une cellule nettement plus faible
        window = [make_reading(cell_v, 5.0, 25.0) for _ in range(10)]
        features = extract_features(window)
        assert features["v_imbalance"] > 0.3
        assert features["v_cell_min"] == pytest.approx(3.40)
        assert features["v_cell_max"] == pytest.approx(3.75)

    def test_rising_temperature_gives_positive_slope(self):
        window = [make_reading([3.75] * NUM_CELLS, 5.0, 25.0 + i) for i in range(10)]
        features = extract_features(window)
        assert features["temp_slope"] > 0

    def test_r_est_fallback_when_current_barely_changes(self):
        """Si le courant ne varie presque pas entre le debut et la fin de la fenetre,
        la resistance estimee doit utiliser la valeur de repli documentee (0.05)
        plutot qu'une division par un delta quasi nul."""
        window = [make_reading([3.75] * NUM_CELLS, 5.0, 25.0) for _ in range(10)]
        features = extract_features(window)
        assert features["r_est"] == pytest.approx(0.05)

    def test_r_est_computed_when_current_varies_significantly(self):
        cell_v_start = [3.80] * NUM_CELLS
        cell_v_end = [3.70] * NUM_CELLS
        window = [make_reading(cell_v_start, 2.0, 25.0)] + \
                 [make_reading(cell_v_start, 2.0, 25.0) for _ in range(8)] + \
                 [make_reading(cell_v_end, 8.0, 25.0)]
        features = extract_features(window)
        assert features["r_est"] != pytest.approx(0.05)
        assert features["r_est"] > 0

    def test_single_reading_window_does_not_crash(self):
        """dI == 0 forcement (meme lecture au debut et a la fin) -> doit tomber sur
        le repli, pas lever d'exception."""
        window = [make_reading([3.75] * NUM_CELLS, 5.0, 25.0)]
        features = extract_features(window)
        assert features["r_est"] == pytest.approx(0.05)
