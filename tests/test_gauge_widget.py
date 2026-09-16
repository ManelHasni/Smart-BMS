"""
test_gauge_widget.py -- Tests du widget CircularGauge (jauge SOC/SOH).

Necessite une QApplication (creation d'un QWidget reel), fournie par le fixture
qapp de conftest.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from gauge_widget import CircularGauge


class TestCircularGauge:
    def test_set_value_without_animation_is_immediate(self, qapp):
        gauge = CircularGauge(label="SOC", unit="%")
        gauge.set_value(42, animate=False)
        assert gauge.value() == 42
        assert gauge.getDisplayValue() == 42

    def test_value_clamped_to_max(self, qapp):
        gauge = CircularGauge(min_value=0, max_value=100)
        gauge.set_value(150, animate=False)
        assert gauge.value() == 100

    def test_value_clamped_to_min(self, qapp):
        gauge = CircularGauge(min_value=0, max_value=100)
        gauge.set_value(-20, animate=False)
        assert gauge.value() == 0

    def test_color_thresholds_default(self, qapp):
        gauge = CircularGauge()
        assert gauge._color_for_value(10).name() != gauge._color_for_value(90).name()

    def test_custom_thresholds_applied(self, qapp):
        gauge = CircularGauge()
        gauge.set_thresholds(critical=70, warning=85)
        assert gauge.CRITICAL_THRESHOLD == 70
        assert gauge.WARNING_THRESHOLD == 85

    def test_subtitle_updates(self, qapp):
        gauge = CircularGauge()
        gauge.set_subtitle("7.5 AH restant")
        assert gauge._subtitle == "7.5 AH restant"

    def test_value_changed_signal_emitted(self, qapp):
        gauge = CircularGauge()
        received = []
        gauge.valueChanged.connect(received.append)
        gauge.set_value(55, animate=False)
        assert received == [55]
