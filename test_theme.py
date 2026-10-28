"""Tests du theme sombre/clair : palettes, bascule a chaud, persistance, non-regression."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import main as main_module


@pytest.fixture(autouse=True)
def _restore_dark_theme():
    yield
    main_module.apply_theme("dark")


def _lum(hex_color):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class TestPalettes:
    def test_same_keys(self):
        assert set(main_module.THEMES["dark"]) == set(main_module.THEMES["light"])

    def test_apply_theme_updates_globals(self):
        main_module.apply_theme("light")
        assert main_module.BG == main_module.THEMES["light"]["BG"]
        main_module.apply_theme("dark")
        assert main_module.BG == main_module.THEMES["dark"]["BG"]

    def test_unknown_theme_falls_back_to_dark(self):
        main_module.apply_theme("inconnu")
        assert main_module.BG == main_module.THEMES["dark"]["BG"]

    @pytest.mark.parametrize("name", ["dark", "light"])
    def test_text_contrast_is_readable(self, name):
        p = main_module.THEMES[name]
        assert _contrast(p["TEXT"], p["SURFACE"]) >= 7
        assert _contrast(p["MUTED"], p["SURFACE"]) >= 4.5
        assert _contrast(p["MUTED"], p["BG"]) >= 4.5


class TestToggle:
    def test_toggle_switches_and_persists(self, isolated_window):
        win = isolated_window
        assert win.current_theme == "dark"
        win._toggle_theme()
        assert win.current_theme == "light"
        assert win.settings.value("appearance/theme") == "light"
        assert main_module.BG == main_module.THEMES["light"]["BG"]

    def test_toggle_twice_returns_to_dark(self, isolated_window):
        win = isolated_window
        win._toggle_theme()
        win._toggle_theme()
        assert win.current_theme == "dark"
        assert main_module.BG == main_module.THEMES["dark"]["BG"]

    def test_keeps_current_page(self, isolated_window):
        win = isolated_window
        win._navigate_to("reports")
        win._toggle_theme()
        assert win.stack.currentIndex() == win._nav_order.index("reports")

    def test_does_not_duplicate_shortcuts(self, isolated_window):
        from PySide6.QtGui import QShortcut
        win = isolated_window
        before = len(win.findChildren(QShortcut))
        win._toggle_theme()
        win._toggle_theme()
        assert len(win.findChildren(QShortcut)) == before == 7

    def test_keeps_protection_counters_visible(self, isolated_window):
        win = isolated_window
        win.protection_events["cell_overvoltage"] = 3
        win._toggle_theme()
        assert win.event_labels["cell_overvoltage"].text() == "3"
        assert "[3]" in win.alarm_badge.text_lbl.text()

    def test_keeps_scenario(self, isolated_window):
        win = isolated_window
        win._set_scenario("surtension")
        win._toggle_theme()
        assert win.sim.scenario == "surtension"
        assert win.scenario_combo.currentData() == "surtension"

    def test_simulation_still_runs_after_toggle(self, isolated_window):
        win = isolated_window
        for _ in range(3):
            win._step()
        win._toggle_theme()
        tick = win.tick
        for _ in range(3):
            win._step()
        assert win.tick == tick + 3

    def test_saved_light_theme_loaded_at_startup(self, isolated_window):
        win = isolated_window
        win._toggle_theme()
        win2 = main_module.MainWindow()
        assert win2.current_theme == "light"
        win2.close()
