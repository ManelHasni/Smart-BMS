"""
Smart BMS — Dashboard desktop PySide6 (pack LiPo 10S/36V)

Simulation locale + vrai modele Random Forest entraine (battery_rf_model.pkl / battery_scaler.pkl)
charge directement en memoire, sans backend HTTP.

Lancer :
    pip install -r requirements.txt
    python main.py
"""

import sys
import os
import csv
import hashlib
import logging
from collections import deque
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pyqtgraph as pg


class ScrollFriendlyPlotWidget(pg.PlotWidget):
    """PlotWidget qui ignore explicitement la molette au lieu de zoomer -- sans ca,
    survoler un graphique a l'interieur d'une page defilante (QScrollArea) capture
    la molette pour le zoom du graphique et empeche de faire defiler la page, ce qui
    est tres deroutant pour l'utilisateur (bug corrige suite a un retour direct)."""

    def wheelEvent(self, event):
        event.ignore()
from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QColor, QFont, QPainter, QBrush, QPen, QPixmap, QIcon, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QListWidget, QListWidgetItem, QProgressBar, QSizePolicy,
    QFileDialog, QMessageBox, QTabWidget, QDoubleSpinBox, QScrollArea, QInputDialog,
    QLineEdit, QSplashScreen, QDialog, QStackedWidget, QSlider, QComboBox,
)

from battery_model import (
    LiveSimulator, SCENARIOS, SCENARIO_TO_MODEL_LABEL, NUM_CELLS, V_MIN, V_MAX, CHEMISTRIES,
)
from gauge_widget import CircularGauge
from icons import IconLabel, icon_pixmap, icon_qicon, set_button_icon
from history_store import HistoryStore
from recording_store import RecordingStore

def _get_base_dir() -> Path:
    """Chemin de base des ressources (modele, icone...) -- gere le cas d'un .exe
    empaquete par PyInstaller, ou sys.executable remplace __file__."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def _get_writable_dir() -> Path:
    """Dossier ecriture (logs, config) -- toujours a cote de l'executable/script,
    jamais dans le dossier temporaire _MEIPASS (qui est en lecture seule et efface
    a chaque lancement)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


BASE_DIR = _get_base_dir()
WRITABLE_DIR = _get_writable_dir()

# --- Journal fichier persistant (en plus du widget Journal dans l'UI) ---
LOG_DIR = WRITABLE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / f"bms_log_{datetime.now().strftime('%Y%m%d')}.txt",
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger("smart_bms")

DEFAULT_PIN_HASH = hashlib.sha256("1234".encode()).hexdigest()

APP_VERSION = "1.2.0"
APP_BUILD_DATE = "2026-08-16"
ICON_PATH = BASE_DIR / "assets" / "icon.png"

# --- Palette ---
BG = "#0B0F0D"
SURFACE = "#131A17"
BORDER = "#1C2620"
TEXT = "#E8F5EE"
MUTED = "#7C9686"
DIM = "#4E625A"
GREEN = "#59F2A0"
COPPER = "#D98E4A"

FEATURE_ORDER = [
    "pack_v_mean", "v_cell_mean", "v_cell_std", "v_cell_min", "v_cell_max",
    "v_imbalance", "current_mean", "current_std", "temp_mean", "temp_max",
    "temp_slope", "r_est",
]

WINDOW_SIZE = 30


def extract_features(window):
    v_all = np.array([r["cell_v"] for r in window])
    current = np.array([r["current_a"] for r in window])
    temp = np.array([r["temp_c"] for r in window])
    pack_v = v_all.sum(axis=1)

    dI = current[-1] - current[0]
    dV = v_all[-1].mean() - v_all[0].mean()
    r_est = abs(dV / dI) if abs(dI) > 0.5 else 0.05

    return {
        "pack_v_mean": float(pack_v.mean()),
        "v_cell_mean": float(v_all.mean()),
        "v_cell_std": float(v_all.std()),
        "v_cell_min": float(v_all.min()),
        "v_cell_max": float(v_all.max()),
        "v_imbalance": float(v_all.max(axis=1).mean() - v_all.min(axis=1).mean()),
        "current_mean": float(current.mean()),
        "current_std": float(current.std()),
        "temp_mean": float(temp.mean()),
        "temp_max": float(temp.max()),
        "temp_slope": float((temp[-1] - temp[0]) / len(temp)),
        "r_est": float(r_est),
    }


class CellBankWidget(QWidget):
    """Dessine les 10 cellules comme un schema electrique (barres + bornes cuivre)."""

    def __init__(self):
        super().__init__()
        self.voltages = [3.75] * NUM_CELLS
        self.fault_index = None
        self.fault_color = QColor(GREEN)
        self.min_index = None
        self.max_index = None
        self.balancing_indices = []
        self.v_min = V_MIN
        self.v_max = V_MAX
        self.setMinimumHeight(85)
        self.setMaximumHeight(95)

    def set_voltage_range(self, v_min, v_max):
        """Appele quand la chimie de la batterie change : adapte l'echelle des barres."""
        self.v_min = v_min
        self.v_max = v_max
        self.update()

    def set_data(self, voltages, fault_index, fault_color_hex, balancing_indices=None):
        self.voltages = voltages
        self.fault_index = fault_index
        self.fault_color = QColor(fault_color_hex)
        self.min_index = voltages.index(min(voltages))
        self.max_index = voltages.index(max(voltages))
        self.balancing_indices = balancing_indices or []
        self.setToolTip(
            f"Vmax: C{self.max_index+1} ({max(voltages):.3f}V, borne bleue)  |  "
            f"Vmin: C{self.min_index+1} ({min(voltages):.3f}V, borne violette)"
        )
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        margin = 20
        n = NUM_CELLS
        slot_w = (w - 2 * margin) / n
        bar_w = min(slot_w * 0.5, 34)
        bar_top = 16
        bar_bottom = h - 24
        bar_h = bar_bottom - bar_top

        painter.setPen(QPen(QColor(BORDER), 1))
        painter.drawLine(margin, bar_top - 10, w - margin, bar_top - 10)

        painter.setFont(QFont("Consolas", 8))
        for i, v in enumerate(self.voltages):
            cx = margin + slot_w * i + slot_w / 2
            pct = max(0.0, min(1.0, (v - self.v_min) / (self.v_max - self.v_min)))
            fill_h = bar_h * pct
            is_fault = (i == self.fault_index)
            color = self.fault_color if is_fault else QColor(GREEN)
            is_min = (i == self.min_index and i != self.max_index)
            is_max = (i == self.max_index and i != self.min_index)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(BORDER)))
            painter.drawRoundedRect(int(cx - bar_w / 2), int(bar_top), int(bar_w), int(bar_h), 3, 3)

            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(
                int(cx - bar_w / 2), int(bar_bottom - fill_h), int(bar_w), int(fill_h), 3, 3
            )

            # Borne : cuivre normalement, bleue/violette pour signaler Vmax/Vmin (evite
            # une ligne de badge separee et garde le widget compact)
            terminal_color = "#7CC3F5" if is_max else ("#B388FF" if is_min else COPPER)
            painter.setPen(QPen(QColor(terminal_color)))
            painter.setBrush(QBrush(QColor(terminal_color)))
            painter.drawEllipse(int(cx - 3), int(bar_bottom + 4), 6, 6)

            if i in self.balancing_indices:
                painter.setPen(QPen(QColor("#F5B942"), 1.5))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(int(cx - 6), int(bar_bottom + 3), 12, 12)

            painter.setPen(QPen(QColor(MUTED)))
            painter.drawText(int(cx - 18), int(bar_top - 13), 36, 11, Qt.AlignCenter, f"{v:.2f}")
            label_color = terminal_color if (is_min or is_max) else DIM
            painter.setPen(QPen(QColor(label_color)))
            painter.drawText(int(cx - 18), int(bar_bottom + 12), 36, 11, Qt.AlignCenter, f"C{i+1}")

        painter.end()


class FleetPack:
    """Represente un pack de la flotte, simule independamment du pack 'actif' affiche
    dans le dashboard detaille. Utilise une verification de seuils simplifiee (pas le
    modele Random Forest complet) pour rester leger meme avec plusieurs packs en //."""

    def __init__(self, name, chemistry="liion", scenario="normal"):
        self.name = name
        self.sim = LiveSimulator(chemistry=chemistry)
        self.sim.set_scenario(scenario)
        self.tick = 0

    def step(self):
        reading = self.sim.step()
        self.tick += 1
        voltages = reading["cell_v"]
        temp = reading["temp_c"]
        soc = self.sim.cells[0].soc * 100
        soh = reading["soh"]
        v_max, v_min = max(voltages), min(voltages)

        status = "normal"
        if v_max >= self.sim.v_max or v_min <= self.sim.v_min or temp >= 55:
            status = "alarme"
        elif v_max >= self.sim.v_max - 0.05 or v_min <= self.sim.v_min + 0.10 or temp >= 45:
            status = "surveillance"

        return {
            "soc": soc, "soh": soh, "temp": temp, "status": status,
            "v_max": v_max, "v_min": v_min, "scenario": self.sim.scenario,
        }


class FleetCard(QFrame):
    """Carte resumee d'un pack de la flotte (nom, statut, SOC/SOH, temperature)."""

    STATUS_STYLE = {
        "normal": (GREEN, "Normal"),
        "surveillance": ("#F5B942", "Surveillance"),
        "alarme": ("#FF5C4D", "Alarme"),
    }

    def __init__(self, name):
        super().__init__()
        self.setStyleSheet(f"background:{SURFACE}; border:1px solid {BORDER}; border-radius:8px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        header = QHBoxLayout()
        self.name_lbl = QLabel(name)
        self.name_lbl.setStyleSheet(f"color:{TEXT}; font-family:Consolas; font-size:12px; font-weight:bold; border:none;")
        self.status_lbl = QLabel("--")
        self.status_lbl.setStyleSheet(f"color:{MUTED}; font-size:10px; border:none;")
        header.addWidget(self.name_lbl)
        header.addStretch()
        header.addWidget(self.status_lbl)
        layout.addLayout(header)

        grid = QGridLayout()
        grid.setSpacing(2)
        self.soc_val = self._metric_pair(grid, 0, "SOC")
        self.soh_val = self._metric_pair(grid, 1, "SOH")
        self.temp_val = self._metric_pair(grid, 2, "Temp")
        layout.addLayout(grid)

        self.scenario_lbl = QLabel("")
        self.scenario_lbl.setStyleSheet(f"color:{DIM}; font-size:9px; font-style:italic; border:none; margin-top:4px;")
        layout.addWidget(self.scenario_lbl)

    def _metric_pair(self, grid, col, label):
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color:{MUTED}; font-size:9px; border:none;")
        lbl.setAlignment(Qt.AlignCenter)
        val = QLabel("--")
        val.setStyleSheet(f"color:{TEXT}; font-family:Consolas; font-size:14px; font-weight:bold; border:none;")
        val.setAlignment(Qt.AlignCenter)
        grid.addWidget(lbl, 0, col)
        grid.addWidget(val, 1, col)
        return val

    def update_data(self, data):
        color, label = self.STATUS_STYLE.get(data["status"], (MUTED, "?"))
        self.status_lbl.setText(label)
        self.status_lbl.setStyleSheet(f"color:{color}; font-size:10px; font-weight:bold; border:none;")
        self.setStyleSheet(f"background:{SURFACE}; border:1px solid {color if data['status']!='normal' else BORDER}; border-radius:8px;")
        self.soc_val.setText(f"{data['soc']:.0f}%")
        self.soh_val.setText(f"{data['soh']:.0f}%")
        self.temp_val.setText(f"{data['temp']:.0f}C")
        scenario_label = SCENARIOS.get(data["scenario"], {}).get("label", data["scenario"])
        self.scenario_lbl.setText(scenario_label)


class MetricCard(QFrame):
    def __init__(self, icon_name, title, unit=""):
        super().__init__()
        self.unit = unit
        self.setStyleSheet(f"background:{SURFACE}; border:1px solid {BORDER}; border-radius:8px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)
        self.title_lbl = IconLabel(icon_name, title.upper(), color=MUTED, size=10, letter_spacing=True)
        self.value_lbl = QLabel("--")
        self.value_lbl.setStyleSheet(f"color:{TEXT}; font-size:16px; font-family:Consolas; border:none;")
        layout.addWidget(self.title_lbl)
        layout.addWidget(self.value_lbl)

    def set_value(self, value, color=TEXT):
        self.value_lbl.setText(f"{value}{self.unit}")
        self.value_lbl.setStyleSheet(f"color:{color}; font-size:16px; font-family:Consolas; border:none;")


class AlarmBadge(QFrame):
    """Badge 'pilule' avec icone vectorielle, remplace le QLabel emoji + gere son propre style."""

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(6)
        self.icon_lbl = QLabel()
        self.icon_lbl.setStyleSheet("background:transparent; border:none;")
        self.text_lbl = QLabel()
        layout.addWidget(self.icon_lbl)
        layout.addWidget(self.text_lbl)
        self.set_state(0)

    def set_state(self, count):
        color = "#F5B942" if count > 0 else MUTED
        border = color if count > 0 else BORDER
        self.icon_lbl.setPixmap(icon_pixmap("bell", color, 13, bg=SURFACE))
        self.text_lbl.setText(f"Alarmes [{count}]")
        self.text_lbl.setStyleSheet(
            f"color:{color}; background:transparent; border:none; font-family:Consolas; font-size:12px;"
        )
        self.setStyleSheet(f"background:{SURFACE}; border:1px solid {border}; border-radius:14px;")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart BMS — Pack LiPo 10S/36V")
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setMinimumSize(1000, 650)
        self.resize(1180, 780)
        self.setStyleSheet(f"background:{BG}; color:{TEXT};")

        self.rf_model = joblib.load(BASE_DIR / "battery_rf_model.pkl")
        self.scaler = joblib.load(BASE_DIR / "battery_scaler.pkl")

        self.settings = QSettings("Akkurad", "SmartBMS")

        saved_chemistry = self.settings.value("chemistry/selected", "liion")
        if saved_chemistry not in CHEMISTRIES:
            saved_chemistry = "liion"
        self.sim = LiveSimulator(chemistry=saved_chemistry)

        # --- Flotte : autres packs simules en parallele, supervision d'ensemble
        # (independants du pack 'actif' ci-dessus, qui reste le sujet du dashboard detaille) ---
        FLEET_PRESETS = [
            ("Velomobile A1", "liion", "normal"),
            ("Velomobile A2", "liion", "desequilibre"),
            ("E-bike B1", "lifepo4", "normal"),
            ("E-bike B2", "liion", "surtension"),
            ("Velomobile A3", "sodium", "normal"),
        ]
        self.fleet = [FleetPack(n, c, s) for n, c, s in FLEET_PRESETS]
        self.fleet_cards = {}

        # --- Historique long terme (multi-session, SQLite) ---
        self.history_store = HistoryStore(WRITABLE_DIR / "history.db")
        self.recording_store = RecordingStore(WRITABLE_DIR / "recordings")
        retention_days = int(self.settings.value("history/retention_days", 90))
        purged = self.history_store.purge_older_than(retention_days)
        if purged:
            logger.info(f"Historique long terme : {purged} points purges (retention {retention_days}j)")
        last_soh = self.history_store.get_last_soh()
        if last_soh is not None:
            self.sim.soh = last_soh  # reprend le vieillissement la ou il en etait
        last_cycles = self.history_store.get_last_cycles()

        self.buffer = deque(maxlen=WINDOW_SIZE)
        self.history_v = deque(maxlen=120)
        self.history_i = deque(maxlen=120)
        self.history_temp = deque(maxlen=120)
        self.soh_history = deque(maxlen=300)  # (tick, soh) pour la regression RUL
        self.tick = 0
        self.last_scenario = "normal"
        self.last_label = "normal"
        self.last_confidence = 0.0
        self.last_probabilities = {}
        self.last_snapshot = None
        self.risk_level = "OK"

        # --- Parametres de protection (modifiables via l'onglet Parametres) ---
        chem_profile = CHEMISTRIES[saved_chemistry]
        DEFAULT_PARAMS = {
            "overvoltage": chem_profile["default_overvoltage"],
            "overvoltage_release": chem_profile["default_overvoltage_release"],
            "undervoltage": chem_profile["default_undervoltage"],
            "undervoltage_release": chem_profile["default_undervoltage_release"],
            "charge_overcurrent": 30.0,
            "discharge_overcurrent": 50.0,
            "short_circuit_current": 80.0,
            "charge_over_temperature": 50.0,
            "discharge_over_temperature": 55.0,
            "balance_turn_on": chem_profile["default_overvoltage"] - 0.20,
            "balancing_precision": 0.03,
        }
        # Recharge la config sauvegardee (QSettings) si elle existe, sinon valeurs par defaut
        self.protection_params = {
            key: float(self.settings.value(f"protection/{key}", default))
            for key, default in DEFAULT_PARAMS.items()
        }
        self.pin_hash = self.settings.value("security/pin_hash", DEFAULT_PIN_HASH)
        # Compteurs d'evenements (declenchement par front montant, pas par tick)
        # Separes charge/decharge, comme sur les BMS commerciaux (SZLLT, ANT BMS)
        self.protection_events = {
            "cell_overvoltage": 0,
            "cell_undervoltage": 0,
            "charge_overcurrent": 0,
            "discharge_overcurrent": 0,
            "charge_over_temperature": 0,
            "discharge_over_temperature": 0,
            "short_circuit": 0,
        }
        self._event_flags = {k: False for k in self.protection_events}

        # --- Compteur de cycles (front montant/descendant sur le SOC, comme un vrai BMS) ---
        self.battery_cycles = int(self.settings.value("session/battery_cycles", 0))
        if last_cycles is not None:
            self.battery_cycles = max(self.battery_cycles, last_cycles)
        self._cycle_armed_low = False

        # --- AutoBalance (commande explicite, separee du seuil de declenchement) ---
        self.autobalance_enabled = self.settings.value("relay/autobalance_enabled", True, type=bool)
        self.sim.set_autobalance(self.autobalance_enabled)
        self.sim.set_balance_params(self.protection_params["balance_turn_on"], self.protection_params["balancing_precision"])

        # --- Commandes relais (simulent ChgMos / DisMos) ---
        self.charge_enabled = self.settings.value("relay/charge_enabled", True, type=bool)
        self.discharge_enabled = self.settings.value("relay/discharge_enabled", True, type=bool)

        # --- Historique complet de session (pour export CSV) ---
        self.full_history = []

        # --- Valeurs de session (depuis le lancement du dashboard) ---
        self.session_start = datetime.now()
        self.session_min_v = None
        self.session_max_v = None
        self.session_max_charge_p = 0.0
        self.session_max_discharge_p = 0.0

        self._build_ui()

        self.timer = QTimer()
        self.timer.timeout.connect(self._step)
        self.timer.start(1000)

    def resizeEvent(self, event):
        """Force un repaint complet lors du redimensionnement pour eviter les residus
        visuels (chevauchements) parfois observes sous Windows avec des QFrame stylisees."""
        super().resizeEvent(event)
        self.centralWidget().update()

    # ---------------------------------------------------------------- UI ---
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("Smart BMS  <span style='color:%s'>10S / 36V</span>" % COPPER)
        title.setTextFormat(Qt.RichText)
        title.setStyleSheet("font-size:22px; font-weight:bold;")
        subtitle = QLabel("Diagnostic predictif — pack LiPo micro-mobilite electrique")
        subtitle.setStyleSheet(f"color:{MUTED}; font-size:12px;")
        title_box = QVBoxLayout()
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        self.status_pill = QLabel("NORMAL")
        self.status_pill.setStyleSheet(
            f"background:{GREEN}22; color:{GREEN}; border:1px solid {GREEN}; "
            "border-radius:14px; padding:6px 16px; font-family:Consolas; font-size:12px;"
        )
        header.addWidget(self.status_pill, alignment=Qt.AlignVCenter)

        self.alarm_badge = AlarmBadge()
        header.addWidget(self.alarm_badge, alignment=Qt.AlignVCenter)

        about_btn = QPushButton()
        set_button_icon(about_btn, "info", MUTED, size=15, bg=SURFACE)
        about_btn.setCursor(Qt.PointingHandCursor)
        about_btn.setFixedSize(30, 30)
        about_btn.setStyleSheet(f"""
            QPushButton {{
                background:{SURFACE}; border:1px solid {BORDER};
                border-radius:15px; margin-left:8px;
            }}
            QPushButton:hover {{ border-color:{COPPER}; }}
        """)
        about_btn.setToolTip("A propos de Smart BMS")
        about_btn.clicked.connect(lambda: AboutDialog(self).exec())
        header.addWidget(about_btn, alignment=Qt.AlignVCenter)

        legend_btn = QPushButton()
        set_button_icon(legend_btn, "help-circle", MUTED, size=15, bg=SURFACE)
        legend_btn.setCursor(Qt.PointingHandCursor)
        legend_btn.setFixedSize(30, 30)
        legend_btn.setStyleSheet(f"""
            QPushButton {{
                background:{SURFACE}; border:1px solid {BORDER};
                border-radius:15px; margin-left:6px;
            }}
            QPushButton:hover {{ border-color:{COPPER}; }}
        """)
        legend_btn.setToolTip("Legende des couleurs et symboles")
        legend_btn.clicked.connect(lambda: LegendDialog(self).exec())
        header.addWidget(legend_btn, alignment=Qt.AlignVCenter)
        root.addLayout(header)

        # --- Barre de navigation : chaque bouton affiche une page entierement differente
        # (QStackedWidget), au lieu d'onglets partages dans un petit panneau lateral. ---
        navbar = QHBoxLayout()
        navbar.setSpacing(8)
        self.nav_buttons = {}
        NAV_ITEMS = [
            ("diagnostic", "activity", "  Diagnostic"),
            ("configuration", "gear", "  Configuration"),
            ("reports", "file-text", "  Rapports"),
            ("fleet", "grid", "  Flotte"),
        ]
        NAV_SHORTCUTS = {"diagnostic": "Ctrl+1", "configuration": "Ctrl+2", "reports": "Ctrl+3", "fleet": "Ctrl+4"}
        for key, icon_name, label in NAV_ITEMS:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            set_button_icon(btn, icon_name, TEXT if key == "diagnostic" else MUTED, size=14, bg=SURFACE if key == "diagnostic" else BG)
            btn.setStyleSheet(self._nav_button_style(active=(key == "diagnostic")))
            btn.setToolTip(NAV_SHORTCUTS.get(key, ""))
            btn.clicked.connect(lambda _, k=key: self._navigate_to(k))
            navbar.addWidget(btn)
            self.nav_buttons[key] = btn
        navbar.addStretch()
        root.addLayout(navbar)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, stretch=1)
        self._nav_order = [key for key, _, _ in NAV_ITEMS]

        # ============================================================
        # PAGE 1 : DIAGNOSTIC (monitoring temps reel)
        # ============================================================
        page_diagnostic = QWidget()
        page_diag_layout = QVBoxLayout(page_diagnostic)
        page_diag_layout.setContentsMargins(0, 0, 0, 0)
        page_diag_layout.setSpacing(12)

        # -- Barre de simulation compacte (mode demo) : discrete, comme un outil de
        # test dans un vrai logiciel professionnel, pas une rangee de gros boutons colores --
        scenario_bar = QFrame()
        scenario_bar.setStyleSheet(f"background:{SURFACE}; border:1px solid {BORDER}; border-radius:6px;")
        scenario_bar_layout = QHBoxLayout(scenario_bar)
        scenario_bar_layout.setContentsMargins(12, 5, 12, 5)
        scenario_bar_layout.setSpacing(8)

        scenario_icon_lbl = QLabel()
        scenario_icon_lbl.setPixmap(icon_pixmap("sliders", MUTED, 13))
        scenario_icon_lbl.setStyleSheet("background:transparent; border:none;")
        scenario_bar_layout.addWidget(scenario_icon_lbl)

        scenario_bar_label = QLabel("Mode simulation — scenario :")
        scenario_bar_label.setStyleSheet(f"color:{MUTED}; font-size:10px; border:none;")
        scenario_bar_layout.addWidget(scenario_bar_label)

        self.scenario_combo = QComboBox()
        for key, info in SCENARIOS.items():
            self.scenario_combo.addItem(info["label"], key)
        self.scenario_combo.setCursor(Qt.PointingHandCursor)
        self.scenario_combo.setStyleSheet(f"""
            QComboBox {{
                background:{BG}; color:{TEXT}; border:1px solid {BORDER};
                border-radius:4px; padding:4px 8px; font-family:Consolas; font-size:10px;
                min-width: 190px;
            }}
            QComboBox::drop-down {{ border:none; }}
        """)
        self.scenario_combo.currentIndexChanged.connect(self._on_scenario_combo_changed)
        scenario_bar_layout.addWidget(self.scenario_combo)

        self.scenario_status_dot = QLabel("\u25CF")
        self.scenario_status_dot.setStyleSheet(f"color:{SCENARIOS['normal']['color']}; font-size:13px; border:none;")
        scenario_bar_layout.addWidget(self.scenario_status_dot)

        scenario_bar_layout.addStretch()
        scenario_bar_hint = QLabel("Demonstration uniquement — sans effet sur un pack reel")
        scenario_bar_hint.setStyleSheet(f"color:{DIM}; font-size:9px; font-style:italic; border:none;")
        scenario_bar_layout.addWidget(scenario_bar_hint)
        page_diag_layout.addWidget(scenario_bar)

        # Metric cards
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(10)
        self.card_voltage = MetricCard("zap", "Tension pack", " V")
        self.card_current = MetricCard("plug", "Courant", " A")
        self.card_temp = MetricCard("thermometer", "Temperature", " C")
        self.card_imbalance = MetricCard("scale", "Desequilibre", " V")
        for c in [self.card_voltage, self.card_current, self.card_temp, self.card_imbalance]:
            metrics_row.addWidget(c)

        control_frame = QFrame()
        control_frame.setStyleSheet(f"background:{SURFACE}; border:1px solid {BORDER}; border-radius:8px;")
        control_layout = QVBoxLayout(control_frame)
        control_layout.setContentsMargins(10, 6, 10, 6)
        control_layout.setSpacing(3)
        control_title = IconLabel("sliders", "COMMANDES", color=MUTED, size=10, letter_spacing=True)
        control_layout.addWidget(control_title)

        self.charge_toggle = QPushButton(f"Charge : {'ON' if self.charge_enabled else 'OFF'}")
        self.charge_toggle.setCheckable(True)
        self.charge_toggle.setChecked(self.charge_enabled)
        self.charge_toggle.setCursor(Qt.PointingHandCursor)
        self.charge_toggle.setStyleSheet(self._toggle_style(self.charge_enabled))
        self.charge_toggle.clicked.connect(self._toggle_charge)

        self.discharge_toggle = QPushButton(f"Discharge : {'ON' if self.discharge_enabled else 'OFF'}")
        self.discharge_toggle.setCheckable(True)
        self.discharge_toggle.setChecked(self.discharge_enabled)
        self.discharge_toggle.setCursor(Qt.PointingHandCursor)
        self.discharge_toggle.setStyleSheet(self._toggle_style(self.discharge_enabled))
        self.discharge_toggle.clicked.connect(self._toggle_discharge)

        self.autobalance_toggle = QPushButton(f"AutoBalance : {'ON' if self.autobalance_enabled else 'OFF'}")
        self.autobalance_toggle.setCheckable(True)
        self.autobalance_toggle.setChecked(self.autobalance_enabled)
        self.autobalance_toggle.setCursor(Qt.PointingHandCursor)
        self.autobalance_toggle.setStyleSheet(self._toggle_style(self.autobalance_enabled))
        self.autobalance_toggle.clicked.connect(self._toggle_autobalance)

        control_layout.addWidget(self.charge_toggle)
        control_layout.addWidget(self.discharge_toggle)
        control_layout.addWidget(self.autobalance_toggle)

        self.balancing_lbl = QLabel("Cellules en equilibrage : 0")
        self.balancing_lbl.setStyleSheet(f"color:{DIM}; font-family:Consolas; font-size:9px; border:none; margin-top:2px;")
        control_layout.addWidget(self.balancing_lbl)
        metrics_row.addWidget(control_frame)

        gauge_box = QFrame()
        gauge_box.setStyleSheet(f"background:{SURFACE}; border:1px solid {BORDER}; border-radius:8px;")
        gauge_outer = QVBoxLayout(gauge_box)
        gauge_row = QHBoxLayout()

        self.soc_gauge = CircularGauge(
            label="SOC", unit="%",
            track_color=BORDER, value_text_color=TEXT, label_text_color=MUTED,
            subtitle_text_color=DIM, normal_color=GREEN, warning_color="#F5B942",
            critical_color="#FF5C4D",
        )
        self.soh_gauge = CircularGauge(
            label="SOH", unit="%",
            track_color=BORDER, value_text_color=TEXT, label_text_color=MUTED,
            subtitle_text_color=DIM, normal_color=COPPER, warning_color="#F5B942",
            critical_color="#FF5C4D",
        )
        self.soh_gauge.set_thresholds(critical=80, warning=90)
        gauge_row.addWidget(self.soc_gauge)
        gauge_row.addWidget(self.soh_gauge)
        gauge_outer.addLayout(gauge_row)

        self.soh_trend_lbl = QLabel("Tendance : --")
        self.soh_trend_lbl.setAlignment(Qt.AlignCenter)
        self.soh_trend_lbl.setStyleSheet(f"color:{DIM}; font-size:9px; font-family:Consolas; border:none;")
        gauge_outer.addWidget(self.soh_trend_lbl)
        metrics_row.addWidget(gauge_box, stretch=1)
        page_diag_layout.addLayout(metrics_row)

        # Cell bank
        cell_frame = QFrame()
        cell_frame.setStyleSheet(f"background:{SURFACE}; border:1px solid {BORDER}; border-radius:8px;")
        cell_layout = QVBoxLayout(cell_frame)
        cell_header = QHBoxLayout()
        cell_title = IconLabel("battery", "BANC DE CELLULES (10S)", color=MUTED, size=12, letter_spacing=True)
        self.cell_delta_lbl = QLabel("delta V: 0.000")
        self.cell_delta_lbl.setStyleSheet(f"color:{MUTED}; font-family:Consolas; font-size:10px; font-weight:bold; border:none;")
        cell_header.addWidget(cell_title)
        cell_header.addStretch()
        cell_header.addWidget(self.cell_delta_lbl)
        cell_layout.addLayout(cell_header)
        self.cell_bank = CellBankWidget()
        self.cell_bank.set_voltage_range(self.sim.v_min, self.sim.v_max)
        cell_layout.addWidget(self.cell_bank)
        page_diag_layout.addWidget(cell_frame)

        # ============================================================
        # Deux graphiques cote a cote (compacts) : telemetrie + RUL
        # ============================================================
        charts_row = QHBoxLayout()
        charts_row.setSpacing(12)

        chart_frame = QFrame()
        chart_frame.setStyleSheet(f"background:{SURFACE}; border:1px solid {BORDER}; border-radius:8px;")
        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.setContentsMargins(10, 6, 10, 6)
        chart_title = IconLabel("activity", "TELEMETRIE TEMPS REEL", color=MUTED, size=10, letter_spacing=True)
        chart_layout.addWidget(chart_title)

        pg.setConfigOption("background", SURFACE)
        pg.setConfigOption("foreground", MUTED)
        self.plot = ScrollFriendlyPlotWidget()
        self.plot.setFixedHeight(150)
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        self.plot.addLegend()
        self.plot.getPlotItem().getViewBox().setMouseEnabled(x=False, y=False)
        self.plot.getPlotItem().setMenuEnabled(False)
        self.plot.getPlotItem().hideButtons()
        self.curve_v = self.plot.plot(pen=pg.mkPen(GREEN, width=2), name="V moy/cell (x10)")
        self.curve_i = self.plot.plot(pen=pg.mkPen("#7CC3F5", width=1.5), name="Courant (A)")
        chart_layout.addWidget(self.plot)
        charts_row.addWidget(chart_frame, stretch=1)

        rul_frame = QFrame()
        rul_frame.setStyleSheet(f"background:{SURFACE}; border:1px solid {BORDER}; border-radius:8px;")
        rul_layout = QVBoxLayout(rul_frame)
        rul_layout.setContentsMargins(10, 6, 10, 6)
        rul_title = IconLabel("trending-down", "ESTIMATION RUL", color=MUTED, size=10, letter_spacing=True)
        rul_layout.addWidget(rul_title)

        self.rul_plot = ScrollFriendlyPlotWidget()
        self.rul_plot.setFixedHeight(150)
        self.rul_plot.showGrid(x=False, y=True, alpha=0.15)
        self.rul_plot.getAxis("left").setLabel("SOH %")
        self.rul_plot.getPlotItem().getViewBox().setMouseEnabled(x=False, y=False)
        self.rul_plot.getPlotItem().setMenuEnabled(False)
        self.rul_plot.getPlotItem().hideButtons()
        self.rul_curve = self.rul_plot.plot(pen=pg.mkPen(COPPER, width=2))
        self.rul_projection_curve = self.rul_plot.plot(
            pen=pg.mkPen("#F5B942", width=1.5, style=Qt.DashLine)
        )
        self.rul_threshold_line = pg.InfiniteLine(
            pos=80, angle=0, pen=pg.mkPen("#FF5C4D", width=1, style=Qt.DotLine)
        )
        self.rul_plot.addItem(self.rul_threshold_line)
        rul_layout.addWidget(self.rul_plot)

        self.rul_stats_lbl = QLabel("Collecte de donnees en cours...")
        self.rul_stats_lbl.setWordWrap(True)
        self.rul_stats_lbl.setStyleSheet(f"color:{MUTED}; font-size:9px; font-family:Consolas; border:none;")
        rul_layout.addWidget(self.rul_stats_lbl)
        charts_row.addWidget(rul_frame, stretch=1)
        page_diag_layout.addLayout(charts_row)

        # ============================================================
        # Diagnostic ML : explicabilite (gauche) + resultat/probabilites (droite)
        # ============================================================
        main_row = QHBoxLayout()
        main_row.setSpacing(12)

        # -- Colonne gauche : explicabilite --
        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        explain_frame = QFrame()
        explain_frame.setStyleSheet(f"background:{SURFACE}; border:1px solid {BORDER}; border-radius:8px;")
        explain_layout = QVBoxLayout(explain_frame)
        explain_title = IconLabel("info", "POURQUOI CE DIAGNOSTIC ?", color=MUTED, size=12, letter_spacing=True)
        explain_layout.addWidget(explain_title)

        self.explain_bars = {}
        FEATURE_LABELS = {
            "pack_v_mean": "Tension pack", "v_cell_mean": "Tension cell. moy.",
            "v_cell_std": "Ecart-type tension", "v_cell_min": "Tension cell. min",
            "v_cell_max": "Tension cell. max", "v_imbalance": "Desequilibre cellules",
            "current_mean": "Courant moyen", "current_std": "Variabilite courant",
            "temp_mean": "Temperature moy.", "temp_max": "Temperature max",
            "temp_slope": "Pente temperature", "r_est": "Resistance estimee",
        }
        self.FEATURE_LABELS = FEATURE_LABELS
        for feat in FEATURE_ORDER:
            row = QHBoxLayout()
            lbl = QLabel(FEATURE_LABELS.get(feat, feat))
            lbl.setFixedWidth(140)
            lbl.setStyleSheet(f"color:{MUTED}; font-size:9px; border:none;")
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            bar.setRange(0, 100)
            bar.setStyleSheet(self._progress_style(COPPER))
            row.addWidget(lbl)
            row.addWidget(bar)
            explain_layout.addLayout(row)
            self.explain_bars[feat] = bar

        self.explain_sentence = QLabel("")
        self.explain_sentence.setWordWrap(True)
        self.explain_sentence.setStyleSheet(f"color:{DIM}; font-size:9px; font-style:italic; border:none; margin-top:4px;")
        explain_layout.addWidget(self.explain_sentence)
        left_col.addWidget(explain_frame)
        main_row.addLayout(left_col, stretch=1)

        # -- Colonne droite : resultat du diagnostic + probabilites --
        diag_frame = QFrame()
        diag_frame.setStyleSheet(f"background:{SURFACE}; border:1px solid {BORDER}; border-radius:8px;")
        diag_layout = QVBoxLayout(diag_frame)
        diag_title = IconLabel("cpu", "DIAGNOSTIC (RANDOM FOREST)", color=MUTED, size=12, letter_spacing=True)
        diag_layout.addWidget(diag_title)
        self.diag_label = QLabel("Normal")
        self.diag_label.setStyleSheet(f"color:{GREEN}; font-family:Consolas; font-size:14px; border:none;")
        self.diag_desc = QLabel(SCENARIOS["normal"]["desc"])
        self.diag_desc.setWordWrap(True)
        self.diag_desc.setStyleSheet(f"color:{MUTED}; font-size:11px; border:none;")
        self.diag_conf = QLabel("Confiance : --")
        self.diag_conf.setStyleSheet(f"color:{DIM}; font-size:10px; font-family:Consolas; border:none;")
        diag_layout.addWidget(self.diag_label)
        diag_layout.addWidget(self.diag_desc)
        diag_layout.addWidget(self.diag_conf)

        proba_title = QLabel("REPARTITION DES PROBABILITES")
        proba_title.setStyleSheet(f"color:{MUTED}; font-size:9px; letter-spacing:1px; border:none; margin-top:6px;")
        diag_layout.addWidget(proba_title)
        self.proba_bars = {}
        self.proba_labels = {}
        for key, info in SCENARIOS.items():
            row = QHBoxLayout()
            lbl = QLabel(info["label"])
            lbl.setFixedWidth(140)
            lbl.setStyleSheet(f"color:{MUTED}; font-size:9px; border:none;")
            bar = QProgressBar()
            bar.setTextVisible(True)
            bar.setFixedHeight(12)
            bar.setStyleSheet(self._progress_style(info["color"]))
            row.addWidget(lbl)
            row.addWidget(bar)
            diag_layout.addLayout(row)
            self.proba_bars[SCENARIO_TO_MODEL_LABEL[key]] = bar
        diag_layout.addStretch()
        main_row.addWidget(diag_frame, stretch=1)
        page_diag_layout.addLayout(main_row)

        # ============================================================

        self.stack.addWidget(self._scrollable(page_diagnostic))

        # -- Onglet 2 : Rapport + journal --
        reports_tab = QWidget()
        reports_outer = QVBoxLayout(reports_tab)
        reports_outer.setContentsMargins(4, 8, 4, 4)
        reports_columns = QHBoxLayout()
        reports_columns.setSpacing(12)
        reports_left_col = QVBoxLayout()
        reports_left_col.setSpacing(8)
        reports_right_col = QVBoxLayout()
        reports_right_col.setSpacing(8)
        reports_columns.addLayout(reports_left_col, stretch=1)
        reports_columns.addLayout(reports_right_col, stretch=1)
        reports_outer.addLayout(reports_columns)
        # Alias conserve pour ne pas modifier chaque appel individuellement plus bas --
        # tous les blocs "gauche" (export, journal, rejeu) utilisent ce nom.
        reports_tab_layout = reports_left_col

        report_frame = QFrame()
        report_frame.setStyleSheet(f"background:{BG}; border:1px solid {BORDER}; border-radius:8px;")
        report_layout = QVBoxLayout(report_frame)
        report_title = IconLabel("file-text", "RAPPORT OPERATEUR", color=MUTED, size=12, letter_spacing=True)
        report_layout.addWidget(report_title)
        report_sub = QLabel("PDF simplifie, lisible sans connaissance technique.")
        report_sub.setWordWrap(True)
        report_sub.setStyleSheet(f"color:{DIM}; font-size:9px; border:none;")
        report_layout.addWidget(report_sub)
        self.export_btn = QPushButton("  Exporter le diagnostic (PDF)")
        self.export_btn.setCursor(Qt.PointingHandCursor)
        set_button_icon(self.export_btn, "download", "#141414", size=13, bg=COPPER)
        self.export_btn.setStyleSheet(f"""
            QPushButton {{
                background:{COPPER}; color:#141414; border:none; border-radius:6px;
                padding:10px; font-family:Consolas; font-size:11px; font-weight:bold;
            }}
            QPushButton:hover {{ background:#E8A159; }}
        """)
        self.export_btn.clicked.connect(self._export_pdf)
        self.export_btn.setToolTip("Ctrl+E")
        report_layout.addWidget(self.export_btn)

        self.export_csv_btn = QPushButton("  Exporter les donnees (CSV)")
        self.export_csv_btn.setCursor(Qt.PointingHandCursor)
        set_button_icon(self.export_csv_btn, "folder-down", MUTED, size=13, bg=BG)
        self.export_csv_btn.setStyleSheet(self._button_style(MUTED, active=False))
        self.export_csv_btn.clicked.connect(self._export_csv)
        self.export_csv_btn.setToolTip("Ctrl+Shift+E")
        report_layout.addWidget(self.export_csv_btn)

        self.export_full_btn = QPushButton("  Rapport complet (PDF, 3 pages)")
        self.export_full_btn.setCursor(Qt.PointingHandCursor)
        set_button_icon(self.export_full_btn, "layers", MUTED, size=13, bg=BG)
        self.export_full_btn.setStyleSheet(self._button_style(MUTED, active=False))
        self.export_full_btn.clicked.connect(self._export_full_report)
        report_layout.addWidget(self.export_full_btn)
        reports_tab_layout.addWidget(report_frame)

        log_frame = QFrame()
        log_frame.setStyleSheet(f"background:{BG}; border:1px solid {BORDER}; border-radius:8px;")
        log_layout = QVBoxLayout(log_frame)
        log_title = IconLabel("list", "JOURNAL", color=MUTED, size=12, letter_spacing=True)
        log_layout.addWidget(log_title)
        self.log_list = QListWidget()
        self.log_list.setStyleSheet(
            f"background:{BG}; border:none; color:{MUTED}; font-family:Consolas; font-size:10px;"
        )
        log_layout.addWidget(self.log_list)
        reports_tab_layout.addWidget(log_frame)

        # -- Rejeu et comparaison de scenarios enregistres --
        replay_frame = QFrame()
        replay_frame.setStyleSheet(f"background:{BG}; border:1px solid {BORDER}; border-radius:8px;")
        replay_layout = QVBoxLayout(replay_frame)
        replay_title = IconLabel("layers", "REJEU ET COMPARAISON DE SCENARIOS", color=MUTED, size=12, letter_spacing=True)
        replay_layout.addWidget(replay_title)
        replay_sub = QLabel("Enregistre la session en cours, puis rejoue-la ou compare deux enregistrements.")
        replay_sub.setWordWrap(True)
        replay_sub.setStyleSheet(f"color:{DIM}; font-size:9px; border:none;")
        replay_layout.addWidget(replay_sub)

        save_recording_btn = QPushButton("  Enregistrer la session actuelle")
        save_recording_btn.setCursor(Qt.PointingHandCursor)
        set_button_icon(save_recording_btn, "save", "#141414", size=13, bg=COPPER)
        save_recording_btn.setStyleSheet(f"""
            QPushButton {{
                background:{COPPER}; color:#141414; border:none; border-radius:6px;
                padding:8px; font-family:Consolas; font-size:10px; font-weight:bold;
            }}
            QPushButton:hover {{ background:#E8A159; }}
        """)
        save_recording_btn.clicked.connect(self._save_recording)
        replay_layout.addWidget(save_recording_btn)

        self.recordings_list = QListWidget()
        self.recordings_list.setStyleSheet(
            f"background:{SURFACE}; border:1px solid {BORDER}; border-radius:6px; "
            f"color:{TEXT}; font-family:Consolas; font-size:10px;"
        )
        self.recordings_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.recordings_list.setFixedHeight(90)
        replay_layout.addWidget(self.recordings_list)

        recording_btn_row = QHBoxLayout()
        replay_btn = QPushButton("  Rejouer")
        replay_btn.setCursor(Qt.PointingHandCursor)
        set_button_icon(replay_btn, "play", GREEN, size=13, bg=BG)
        replay_btn.setStyleSheet(self._button_style(GREEN, active=False))
        replay_btn.clicked.connect(self._replay_selected_recording)
        recording_btn_row.addWidget(replay_btn)

        compare_btn = QPushButton("  Comparer")
        compare_btn.setCursor(Qt.PointingHandCursor)
        set_button_icon(compare_btn, "layers", "#7CC3F5", size=13, bg=BG)
        compare_btn.setStyleSheet(self._button_style("#7CC3F5", active=False))
        compare_btn.clicked.connect(self._compare_selected_recordings)
        recording_btn_row.addWidget(compare_btn)

        delete_recording_btn = QPushButton("  Suppr.")
        delete_recording_btn.setCursor(Qt.PointingHandCursor)
        set_button_icon(delete_recording_btn, "alert-triangle", "#FF5C4D", size=13, bg=BG)
        delete_recording_btn.setStyleSheet(self._button_style("#FF5C4D", active=False))
        delete_recording_btn.clicked.connect(self._delete_selected_recordings)
        recording_btn_row.addWidget(delete_recording_btn)
        replay_layout.addLayout(recording_btn_row)

        reports_tab_layout.addWidget(replay_frame)
        self._refresh_recordings_list()

        # -- Onglet 3 : Parametres de protection + historique des declenchements --
        params_tab = QWidget()
        params_tab_layout = QVBoxLayout(params_tab)
        params_tab_layout.setContentsMargins(4, 8, 4, 4)
        params_tab_layout.setSpacing(8)

        # -- Selecteur de chimie de la batterie (comme sur ANT BMS : LiFePO4 / Li-ion / Sodium-ion) --
        chem_frame = QFrame()
        chem_frame.setStyleSheet(f"background:{BG}; border:1px solid {BORDER}; border-radius:8px;")
        chem_layout = QVBoxLayout(chem_frame)
        chem_title = IconLabel("battery", "CHIMIE DE LA BATTERIE", color=MUTED, size=12, letter_spacing=True)
        chem_layout.addWidget(chem_title)
        chem_sub = QLabel("Change la courbe OCV et la plage de tension simulees. Protege par PIN.")
        chem_sub.setWordWrap(True)
        chem_sub.setStyleSheet(f"color:{DIM}; font-size:9px; border:none;")
        chem_layout.addWidget(chem_sub)

        chem_btn_row = QGridLayout()
        chem_btn_row.setSpacing(6)
        self.chemistry_buttons = {}
        for idx, (key, profile) in enumerate(CHEMISTRIES.items()):
            btn = QPushButton(profile["label"])
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(self._button_style(COPPER, active=(key == self.sim.chemistry)))
            btn.clicked.connect(lambda _, k=key: self._request_chemistry_change(k))
            chem_btn_row.addWidget(btn, idx // 2, idx % 2)
            self.chemistry_buttons[key] = btn
        chem_layout.addLayout(chem_btn_row)

        self.chem_info_lbl = QLabel(self._chemistry_info_text())
        self.chem_info_lbl.setWordWrap(True)
        self.chem_info_lbl.setStyleSheet(f"color:{TEXT}; font-family:Consolas; font-size:9px; border:none; margin-top:4px;")
        chem_layout.addWidget(self.chem_info_lbl)
        params_tab_layout.addWidget(chem_frame)

        params_frame = QFrame()
        params_frame.setStyleSheet(f"background:{BG}; border:1px solid {BORDER}; border-radius:8px;")
        params_layout = QGridLayout(params_frame)
        params_layout.setSpacing(6)
        params_title = IconLabel("shield", "SEUILS DE PROTECTION", color=MUTED, size=12, letter_spacing=True)
        params_layout.addWidget(params_title, 0, 0, 1, 2)

        PARAM_FIELDS = [
            ("overvoltage", "Surtension cellule (V)", 3.0, 4.35, 0.01),
            ("overvoltage_release", "Relachement surtension (V)", 3.0, 4.35, 0.01),
            ("undervoltage", "Sous-tension cellule (V)", 2.5, 4.0, 0.01),
            ("undervoltage_release", "Relachement sous-tension (V)", 2.5, 4.0, 0.01),
            ("charge_overcurrent", "Surintensite charge (A)", 5.0, 100.0, 1.0),
            ("discharge_overcurrent", "Surintensite decharge (A)", 5.0, 200.0, 1.0),
            ("short_circuit_current", "Seuil court-circuit (A)", 20.0, 300.0, 5.0),
            ("charge_over_temperature", "Surchauffe en charge (C)", 30.0, 100.0, 1.0),
            ("discharge_over_temperature", "Surchauffe en decharge (C)", 30.0, 100.0, 1.0),
            ("balance_turn_on", "Seuil declenchement balance (V)", 3.0, 4.3, 0.01),
            ("balancing_precision", "Precision balance (V)", 0.005, 0.2, 0.005),
        ]
        self.param_spinboxes = {}
        spin_style = f"""
            QDoubleSpinBox {{
                background:{SURFACE}; color:{TEXT}; border:1px solid {BORDER};
                border-radius:4px; padding:3px; font-family:Consolas; font-size:10px;
            }}
        """
        for idx, (key, label, lo, hi, step) in enumerate(PARAM_FIELDS):
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{MUTED}; font-size:9px; border:none;")
            spin = QDoubleSpinBox()
            spin.setRange(lo, hi)
            spin.setSingleStep(step)
            spin.setDecimals(3 if step < 0.01 else 2)
            spin.setValue(self.protection_params[key])
            spin.setStyleSheet(spin_style)
            params_layout.addWidget(lbl, idx + 1, 0)
            params_layout.addWidget(spin, idx + 1, 1)
            self.param_spinboxes[key] = spin

        self.apply_params_btn = QPushButton("  Appliquer les seuils")
        self.apply_params_btn.setCursor(Qt.PointingHandCursor)
        set_button_icon(self.apply_params_btn, "check-circle", "#141414", size=13, bg=COPPER)
        self.apply_params_btn.setStyleSheet(f"""
            QPushButton {{
                background:{COPPER}; color:#141414; border:none; border-radius:6px;
                padding:8px; font-family:Consolas; font-size:10px; font-weight:bold;
            }}
            QPushButton:hover {{ background:#E8A159; }}
        """)
        self.apply_params_btn.clicked.connect(self._apply_protection_params)
        params_layout.addWidget(self.apply_params_btn, len(PARAM_FIELDS) + 1, 0, 1, 2)

        change_pin_btn = QPushButton("  Changer le PIN")
        change_pin_btn.setCursor(Qt.PointingHandCursor)
        set_button_icon(change_pin_btn, "lock", MUTED, size=13, bg=BG)
        change_pin_btn.setStyleSheet(self._button_style(MUTED, active=False))
        change_pin_btn.clicked.connect(self._change_pin)
        params_layout.addWidget(change_pin_btn, len(PARAM_FIELDS) + 2, 0, 1, 2)
        params_tab_layout.addWidget(params_frame)

        history_frame = QFrame()
        history_frame.setStyleSheet(f"background:{BG}; border:1px solid {BORDER}; border-radius:8px;")
        history_layout = QVBoxLayout(history_frame)
        history_title = IconLabel("clock", "HISTORIQUE DES DECLENCHEMENTS", color=MUTED, size=12, letter_spacing=True)
        history_layout.addWidget(history_title)

        self.event_labels = {}
        EVENT_TITLES = {
            "cell_overvoltage": ("zap", "Surtension cellule"),
            "cell_undervoltage": ("battery", "Sous-tension cellule"),
            "charge_overcurrent": ("plug", "Surintensite charge"),
            "discharge_overcurrent": ("alert-triangle", "Surintensite decharge"),
            "charge_over_temperature": ("flame", "Surchauffe charge"),
            "discharge_over_temperature": ("flame", "Surchauffe decharge"),
            "short_circuit": ("alert-triangle", "Court-circuit"),
        }
        for key, (icon_name, title) in EVENT_TITLES.items():
            row = QHBoxLayout()
            lbl = IconLabel(icon_name, title, color=MUTED, size=11)
            count_lbl = QLabel("0")
            count_lbl.setStyleSheet(f"color:{TEXT}; font-family:Consolas; font-size:11px; font-weight:bold; border:none;")
            count_lbl.setAlignment(Qt.AlignRight)
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(count_lbl)
            history_layout.addLayout(row)
            self.event_labels[key] = count_lbl

        reset_btn = QPushButton("  Reinitialiser l'historique")
        reset_btn.setCursor(Qt.PointingHandCursor)
        set_button_icon(reset_btn, "refresh-cw", MUTED, size=13, bg=BG)
        reset_btn.setStyleSheet(self._button_style(MUTED, active=False))
        reset_btn.clicked.connect(self._reset_protection_history)
        history_layout.addWidget(reset_btn)

        hist_maint_row = QHBoxLayout()
        hist_maint_row.setSpacing(12)
        hist_maint_row.addWidget(history_frame, stretch=1)

        # -- Actions de maintenance (comme ANT BMS : Reset BMS / Close BMS / Reset Factory) --
        maint_frame = QFrame()
        maint_frame.setStyleSheet(f"background:{BG}; border:1px solid {BORDER}; border-radius:8px;")
        maint_layout = QVBoxLayout(maint_frame)
        maint_title = IconLabel("tool", "MAINTENANCE", color=MUTED, size=12, letter_spacing=True)
        maint_layout.addWidget(maint_title)
        maint_sub = QLabel("Actions protegees par PIN, avec confirmation.")
        maint_sub.setStyleSheet(f"color:{DIM}; font-size:9px; border:none;")
        maint_layout.addWidget(maint_sub)

        reset_bms_btn = QPushButton("  Reset BMS (RAZ compteurs/session)")
        reset_bms_btn.setCursor(Qt.PointingHandCursor)
        set_button_icon(reset_bms_btn, "refresh-cw", "#F5B942", size=13, bg=BG)
        reset_bms_btn.setStyleSheet(self._button_style("#F5B942", active=False))
        reset_bms_btn.clicked.connect(self._reset_bms)
        maint_layout.addWidget(reset_bms_btn)

        close_bms_btn = QPushButton("  Close BMS (coupure Charge + Discharge)")
        close_bms_btn.setCursor(Qt.PointingHandCursor)
        set_button_icon(close_bms_btn, "power", "#FF5C4D", size=13, bg=BG)
        close_bms_btn.setStyleSheet(self._button_style("#FF5C4D", active=False))
        close_bms_btn.clicked.connect(self._close_bms)
        maint_layout.addWidget(close_bms_btn)

        factory_reset_btn = QPushButton("  Reset Factory Settings")
        factory_reset_btn.setCursor(Qt.PointingHandCursor)
        set_button_icon(factory_reset_btn, "alert-triangle", "#FF5C4D", size=13, bg=BG)
        factory_reset_btn.setStyleSheet(self._button_style("#FF5C4D", active=False))
        factory_reset_btn.clicked.connect(self._reset_factory_settings)
        maint_layout.addWidget(factory_reset_btn)

        hist_maint_row.addWidget(maint_frame, stretch=1)
        params_tab_layout.addLayout(hist_maint_row)
        params_tab_layout.addStretch()
        self.stack.addWidget(self._scrollable(params_tab))

        # ============================================================
        # PAGE 3 : RAPPORTS (export PDF/CSV, journal, session, infos appareil)
        # ============================================================
        session_frame = QFrame()
        session_frame.setStyleSheet(f"background:{BG}; border:1px solid {BORDER}; border-radius:8px;")
        session_layout = QVBoxLayout(session_frame)
        session_title = IconLabel("bar-chart", "VALEURS DE SESSION", color=MUTED, size=12, letter_spacing=True)
        session_layout.addWidget(session_title)

        self.session_labels = {}
        SESSION_ROWS = [
            ("min_v", "Tension min"), ("max_v", "Tension max"),
            ("max_charge_p", "Puissance max charge"), ("max_discharge_p", "Puissance max decharge"),
            ("duration", "Duree session"),
        ]
        for key, label in SESSION_ROWS:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{MUTED}; font-size:10px; border:none;")
            val = QLabel("--")
            val.setStyleSheet(f"color:{TEXT}; font-family:Consolas; font-size:11px; font-weight:bold; border:none;")
            val.setAlignment(Qt.AlignRight)
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            session_layout.addLayout(row)
            self.session_labels[key] = val

        reset_session_btn = QPushButton("  Reinitialiser la session")
        reset_session_btn.setCursor(Qt.PointingHandCursor)
        set_button_icon(reset_session_btn, "refresh-cw", MUTED, size=13, bg=BG)
        reset_session_btn.setStyleSheet(self._button_style(MUTED, active=False))
        reset_session_btn.clicked.connect(self._reset_session)
        session_layout.addWidget(reset_session_btn)
        reports_right_col.addWidget(session_frame)

        # -- Historique long terme (multi-session, persiste en SQLite) --
        longterm_frame = QFrame()
        longterm_frame.setStyleSheet(f"background:{BG}; border:1px solid {BORDER}; border-radius:8px;")
        longterm_layout = QVBoxLayout(longterm_frame)
        longterm_title = IconLabel("trending-down", "EVOLUTION DU SOH (LONG TERME)", color=MUTED, size=12, letter_spacing=True)
        longterm_layout.addWidget(longterm_title)

        self.longterm_plot = ScrollFriendlyPlotWidget()
        self.longterm_plot.setFixedHeight(140)
        self.longterm_plot.showGrid(x=False, y=True, alpha=0.15)
        self.longterm_plot.getAxis("left").setLabel("SOH %")
        self.longterm_plot.getAxis("bottom").setLabel("minutes")
        self.longterm_curve = self.longterm_plot.plot(
            pen=pg.mkPen(COPPER, width=2), symbol="o", symbolSize=4,
            symbolBrush=COPPER, symbolPen=None,
        )
        longterm_layout.addWidget(self.longterm_plot)

        self.longterm_stats_lbl = QLabel("Historique en cours de constitution...")
        self.longterm_stats_lbl.setWordWrap(True)
        self.longterm_stats_lbl.setStyleSheet(f"color:{MUTED}; font-size:10px; font-family:Consolas; border:none;")
        longterm_layout.addWidget(self.longterm_stats_lbl)

        purge_row = QHBoxLayout()
        purge_lbl = QLabel("Retention (jours)")
        purge_lbl.setStyleSheet(f"color:{MUTED}; font-size:9px; border:none;")
        self.retention_spin = QDoubleSpinBox()
        self.retention_spin.setRange(1, 3650)
        self.retention_spin.setDecimals(0)
        self.retention_spin.setValue(int(self.settings.value("history/retention_days", 90)))
        self.retention_spin.setStyleSheet(
            f"QDoubleSpinBox {{ background:{SURFACE}; color:{TEXT}; border:1px solid {BORDER}; "
            "border-radius:4px; padding:3px; font-family:Consolas; font-size:10px; }"
        )
        self.retention_spin.valueChanged.connect(self._update_retention)
        purge_row.addWidget(purge_lbl)
        purge_row.addWidget(self.retention_spin)
        longterm_layout.addLayout(purge_row)

        clear_history_btn = QPushButton("  Effacer l'historique long terme")
        clear_history_btn.setCursor(Qt.PointingHandCursor)
        set_button_icon(clear_history_btn, "alert-triangle", "#FF5C4D", size=13, bg=BG)
        clear_history_btn.setStyleSheet(self._button_style("#FF5C4D", active=False))
        clear_history_btn.clicked.connect(self._clear_longterm_history)
        longterm_layout.addWidget(clear_history_btn)

        reports_right_col.addWidget(longterm_frame)
        self._refresh_longterm_chart()

        info_frame = QFrame()
        info_frame.setStyleSheet(f"background:{BG}; border:1px solid {BORDER}; border-radius:8px;")
        info_layout = QVBoxLayout(info_frame)
        info_title = IconLabel("info", "INFOS APPAREIL", color=MUTED, size=12, letter_spacing=True)
        info_layout.addWidget(info_title)

        nominal_ah = self.sim.cells[0].capacity_ah
        pack_nominal_v = NUM_CELLS * CHEMISTRIES[self.sim.chemistry]["v_nominal"]
        DEVICE_INFO = [
            ("Fabricant", "Akkurad GmbH"),
            ("Modele", "Smart BMS — Simulateur"),
            ("Configuration pack", f"{NUM_CELLS}S / {pack_nominal_v:.1f}V nominal"),
            ("Capacite nominale", f"{nominal_ah:.1f} AH"),
            ("Debut de session", self.session_start.strftime("%d/%m/%Y %H:%M:%S")),
        ]
        for label, value in DEVICE_INFO:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{MUTED}; font-size:10px; border:none;")
            val = QLabel(value)
            val.setStyleSheet(f"color:{TEXT}; font-family:Consolas; font-size:10px; border:none;")
            val.setAlignment(Qt.AlignRight)
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            info_layout.addLayout(row)
            if label == "Configuration pack":
                self.pack_config_lbl = val

        cycles_row = QHBoxLayout()
        cycles_lbl_title = QLabel("Cycles de charge/decharge")
        cycles_lbl_title.setStyleSheet(f"color:{MUTED}; font-size:10px; border:none;")
        self.cycles_lbl = QLabel(str(self.battery_cycles))
        self.cycles_lbl.setStyleSheet(f"color:{COPPER}; font-family:Consolas; font-size:11px; font-weight:bold; border:none;")
        self.cycles_lbl.setAlignment(Qt.AlignRight)
        cycles_row.addWidget(cycles_lbl_title)
        cycles_row.addStretch()
        cycles_row.addWidget(self.cycles_lbl)
        info_layout.addLayout(cycles_row)
        reports_right_col.addWidget(info_frame)
        reports_left_col.addStretch()
        reports_right_col.addStretch()
        self.stack.addWidget(self._scrollable(reports_tab))

        # ============================================================
        # PAGE 4 : FLOTTE (supervision de plusieurs packs en parallele)
        # ============================================================
        fleet_tab = QWidget()
        fleet_tab_layout = QVBoxLayout(fleet_tab)
        fleet_tab_layout.setContentsMargins(4, 8, 4, 4)
        fleet_tab_layout.setSpacing(12)

        fleet_intro = QLabel(
            "Ces packs sont simules independamment du pack affiche dans Diagnostic / "
            "Configuration / Rapports -- une supervision d'ensemble typique d'une flotte "
            "de velomobiles/e-bikes Akkurad. Verification par seuils simplifiee (pas le "
            "modele Random Forest complet, pour rester leger avec plusieurs packs en //)."
        )
        fleet_intro.setWordWrap(True)
        fleet_intro.setStyleSheet(f"color:{DIM}; font-size:10px; border:none;")
        fleet_tab_layout.addWidget(fleet_intro)

        fleet_grid = QGridLayout()
        fleet_grid.setSpacing(12)
        for idx, pack in enumerate(self.fleet):
            card = FleetCard(pack.name)
            fleet_grid.addWidget(card, idx // 2, idx % 2)
            self.fleet_cards[pack.name] = card
        fleet_tab_layout.addLayout(fleet_grid)
        fleet_tab_layout.addStretch()
        self.stack.addWidget(self._scrollable(fleet_tab))

        # -- Raccourcis clavier (detail pro apprecie en demo live) --
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self._export_pdf)
        QShortcut(QKeySequence("Ctrl+Shift+E"), self, activated=self._export_csv)
        QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda: self._navigate_to("diagnostic"))
        QShortcut(QKeySequence("Ctrl+2"), self, activated=lambda: self._navigate_to("configuration"))
        QShortcut(QKeySequence("Ctrl+3"), self, activated=lambda: self._navigate_to("reports"))
        QShortcut(QKeySequence("Ctrl+4"), self, activated=lambda: self._navigate_to("fleet"))

    def _navigate_to(self, key):
        """Bascule vers une page entiere (QStackedWidget), et met a jour le style
        de la barre de navigation en consequence."""
        idx = self._nav_order.index(key)
        self.stack.setCurrentIndex(idx)
        NAV_ICONS = {"diagnostic": "activity", "configuration": "gear", "reports": "file-text", "fleet": "grid"}
        for k, btn in self.nav_buttons.items():
            active = (k == key)
            btn.setStyleSheet(self._nav_button_style(active=active))
            set_button_icon(btn, NAV_ICONS[k], TEXT if active else MUTED, size=14,
                             bg=SURFACE if active else BG)

    def _nav_button_style(self, active):
        if active:
            return f"""
                QPushButton {{
                    background:{SURFACE}; color:{TEXT}; border:1px solid {COPPER};
                    border-bottom:3px solid {COPPER}; border-radius:8px;
                    padding:10px 20px; font-family:Consolas; font-size:11px; font-weight:bold;
                }}
            """
        return f"""
            QPushButton {{
                background:{BG}; color:{MUTED}; border:1px solid {BORDER};
                border-radius:8px; padding:10px 20px; font-family:Consolas; font-size:11px;
            }}
            QPushButton:hover {{ color:{TEXT}; border-color:{MUTED}; }}
        """

    def _progress_style(self, color):
        return f"""
            QProgressBar {{
                background:{BORDER}; border:none; border-radius:4px; height:14px;
                text-align:center; color:{TEXT}; font-size:9px;
            }}
            QProgressBar::chunk {{ background:{color}; border-radius:4px; }}
        """

    def _button_style(self, color, active=False):
        bg = f"{color}22" if active else "transparent"
        border = color if active else BORDER
        text = color if active else MUTED
        return f"""
            QPushButton {{
                background:{bg}; color:{text}; border:1px solid {border};
                border-radius:6px; padding:8px; font-family:Consolas; font-size:10px;
            }}
            QPushButton:hover {{ border:1px solid {color}; color:{color}; }}
        """

    def _toggle_style(self, on):
        color = GREEN if on else "#FF5C4D"
        return f"""
            QPushButton {{
                background:{color}22; color:{color}; border:1px solid {color};
                border-radius:5px; padding:3px; font-family:Consolas; font-size:9px; font-weight:bold;
            }}
            QPushButton:hover {{ background:{color}33; }}
        """

    def _scrollable(self, inner_widget):
        """Enveloppe un widget dans un QScrollArea : si le contenu depasse la hauteur
        disponible, une scrollbar apparait au lieu de chevaucher (bug recurrent corrige
        ici de facon definitive, quelle que soit la taille de la fenetre)."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner_widget)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:8px; }}
            QScrollArea > QWidget > QWidget {{ background:{SURFACE}; }}
            QScrollBar:vertical {{ background:{BG}; width:8px; margin:0; }}
            QScrollBar::handle:vertical {{ background:{BORDER}; border-radius:4px; min-height:24px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        """)
        return scroll

    # ------------------------------------------------------------ logic ---
    def _set_scenario(self, key):
        self.sim.set_scenario(key)
        if hasattr(self, "scenario_combo"):
            idx = self.scenario_combo.findData(key)
            if idx != -1 and self.scenario_combo.currentIndex() != idx:
                self.scenario_combo.blockSignals(True)
                self.scenario_combo.setCurrentIndex(idx)
                self.scenario_combo.blockSignals(False)
            self.scenario_status_dot.setStyleSheet(
                f"color:{SCENARIOS[key]['color']}; font-size:13px; border:none;"
            )
        if key != self.last_scenario:
            self._log(f"Etat -> {SCENARIOS[key]['label']}")
            self.last_scenario = key

    def _on_scenario_combo_changed(self, index):
        key = self.scenario_combo.itemData(index)
        if key:
            self._set_scenario(key)

    def _toggle_charge(self):
        self.charge_enabled = self.charge_toggle.isChecked()
        self.charge_toggle.setText(f"Charge : {'ON' if self.charge_enabled else 'OFF'}")
        self.charge_toggle.setStyleSheet(self._toggle_style(self.charge_enabled))
        self.settings.setValue("relay/charge_enabled", self.charge_enabled)
        self._log(f"Commutateur ChgMos -> {'ON' if self.charge_enabled else 'OFF'}")

    def _toggle_discharge(self):
        self.discharge_enabled = self.discharge_toggle.isChecked()
        self.discharge_toggle.setText(f"Discharge : {'ON' if self.discharge_enabled else 'OFF'}")
        self.discharge_toggle.setStyleSheet(self._toggle_style(self.discharge_enabled))
        self.settings.setValue("relay/discharge_enabled", self.discharge_enabled)
        self._log(f"Commutateur DisMos -> {'ON' if self.discharge_enabled else 'OFF'}")

    def _toggle_autobalance(self):
        self.autobalance_enabled = self.autobalance_toggle.isChecked()
        self.autobalance_toggle.setText(f"AutoBalance : {'ON' if self.autobalance_enabled else 'OFF'}")
        self.autobalance_toggle.setStyleSheet(self._toggle_style(self.autobalance_enabled))
        self.sim.set_autobalance(self.autobalance_enabled)
        self.settings.setValue("relay/autobalance_enabled", self.autobalance_enabled)
        self._log(f"AutoBalance -> {'ON' if self.autobalance_enabled else 'OFF'}")
        if not self.autobalance_enabled:
            self.balancing_lbl.setText("Cellules en equilibrage : 0 (desactive)")

    def _log(self, msg):
        from datetime import datetime
        t = datetime.now().strftime("%H:%M:%S")
        self.log_list.insertItem(0, f"{t}  {msg}")
        while self.log_list.count() > 8:
            self.log_list.takeItem(self.log_list.count() - 1)
        logger.info(msg)

    def _check_pin(self, action_desc):
        """Demande le PIN pour une action sensible. Retourne True si valide, sinon
        affiche une erreur, journalise la tentative et retourne False."""
        pin, ok = QInputDialog.getText(
            self, "Code PIN requis", f"Entrer le PIN pour {action_desc} :", QLineEdit.Password,
        )
        if not ok:
            return False
        if hashlib.sha256(pin.encode()).hexdigest() != self.pin_hash:
            QMessageBox.warning(self, "PIN incorrect", "Code PIN invalide. Action annulee.")
            self._log(f"Tentative refusee (PIN incorrect) : {action_desc}")
            return False
        return True

    def _apply_protection_params(self):
        pin, ok = QInputDialog.getText(
            self, "Code PIN requis", "Entrer le PIN pour modifier les seuils de protection :",
            QLineEdit.Password,
        )
        if not ok:
            return
        if hashlib.sha256(pin.encode()).hexdigest() != self.pin_hash:
            QMessageBox.warning(self, "PIN incorrect", "Code PIN invalide. Seuils non modifies.")
            self._log("Tentative de modification des seuils refusee (PIN incorrect)")
            return
        for key, spin in self.param_spinboxes.items():
            self.protection_params[key] = spin.value()
            self.settings.setValue(f"protection/{key}", spin.value())
        self.sim.set_balance_params(self.protection_params["balance_turn_on"], self.protection_params["balancing_precision"])
        self._log("Seuils de protection mis a jour (PIN valide)")

    def _change_pin(self):
        old_pin, ok = QInputDialog.getText(self, "Changer le PIN", "PIN actuel :", QLineEdit.Password)
        if not ok:
            return
        if hashlib.sha256(old_pin.encode()).hexdigest() != self.pin_hash:
            QMessageBox.warning(self, "PIN incorrect", "PIN actuel invalide.")
            return
        new_pin, ok = QInputDialog.getText(self, "Changer le PIN", "Nouveau PIN :", QLineEdit.Password)
        if not ok or not new_pin:
            return
        self.pin_hash = hashlib.sha256(new_pin.encode()).hexdigest()
        self.settings.setValue("security/pin_hash", self.pin_hash)
        self._log("PIN de protection modifie")
        QMessageBox.information(self, "PIN modifie", "Le nouveau PIN est enregistre.")

    def _chemistry_info_text(self):
        p = CHEMISTRIES[self.sim.chemistry]
        pack_v = NUM_CELLS * p["v_nominal"]
        return (f"Plage cellule : {p['v_min']:.2f}V - {p['v_max']:.2f}V   |   "
                f"Nominal : {p['v_nominal']:.2f}V/cellule   |   Pack : {pack_v:.1f}V nominal")

    def _request_chemistry_change(self, key):
        if key == self.sim.chemistry:
            return
        pin, ok = QInputDialog.getText(
            self, "Code PIN requis",
            f"Entrer le PIN pour passer en chimie {CHEMISTRIES[key]['label']} :",
            QLineEdit.Password,
        )
        if not ok:
            return
        if hashlib.sha256(pin.encode()).hexdigest() != self.pin_hash:
            QMessageBox.warning(self, "PIN incorrect", "Code PIN invalide. Chimie non modifiee.")
            self._log("Tentative de changement de chimie refusee (PIN incorrect)")
            return

        reply = QMessageBox.question(
            self, "Confirmer le changement de chimie",
            f"Passer la simulation en {CHEMISTRIES[key]['label']} ?\n\n"
            "Les seuils de surtension/sous-tension seront reinitialises aux valeurs "
            "par defaut de cette chimie (les seuils de courant/temperature sont conserves).",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self._set_chemistry(key)

    def _set_chemistry(self, key):
        old_label = CHEMISTRIES[self.sim.chemistry]["label"]
        self.sim.set_chemistry(key)
        profile = CHEMISTRIES[key]

        # Seuils de tension remis aux valeurs par defaut de la nouvelle chimie
        for pkey, value in [
            ("overvoltage", profile["default_overvoltage"]),
            ("overvoltage_release", profile["default_overvoltage_release"]),
            ("undervoltage", profile["default_undervoltage"]),
            ("undervoltage_release", profile["default_undervoltage_release"]),
            ("balance_turn_on", profile["default_overvoltage"] - 0.20),
        ]:
            self.protection_params[pkey] = value
            self.settings.setValue(f"protection/{pkey}", value)
            if pkey in self.param_spinboxes:
                self.param_spinboxes[pkey].setRange(profile["v_min"] - 0.3, profile["v_max"] + 0.3)
                self.param_spinboxes[pkey].setValue(value)
        self.settings.setValue("chemistry/selected", key)

        self.sim.set_balance_params(self.protection_params["balance_turn_on"], self.protection_params["balancing_precision"])
        self.cell_bank.set_voltage_range(profile["v_min"], profile["v_max"])
        for k, btn in self.chemistry_buttons.items():
            btn.setStyleSheet(self._button_style(COPPER, active=(k == key)))
        self.chem_info_lbl.setText(self._chemistry_info_text())
        if hasattr(self, "pack_config_lbl"):
            self.pack_config_lbl.setText(f"{NUM_CELLS}S / {NUM_CELLS * profile['v_nominal']:.1f}V nominal")

        self._log(f"Chimie changee : {old_label} -> {profile['label']}")

    def _reset_protection_history(self):
        for key in self.protection_events:
            self.protection_events[key] = 0
            self._event_flags[key] = False
            self.event_labels[key].setText("0")
        self._log("Historique des declenchements reinitialise")
        self._update_alarm_badge()

    def _update_alarm_badge(self):
        total = sum(self.protection_events.values())
        self.alarm_badge.set_state(total)

    def _reset_session(self):
        self.session_start = datetime.now()
        self.session_min_v = None
        self.session_max_v = None
        self.session_max_charge_p = 0.0
        self.session_max_discharge_p = 0.0
        self._log("Session reinitialisee")

    def _update_retention(self, value):
        days = int(value)
        self.settings.setValue("history/retention_days", days)
        purged = self.history_store.purge_older_than(days)
        if purged:
            self._log(f"Historique long terme : {purged} points purges (retention {days}j)")
            self._refresh_longterm_chart()

    def _clear_longterm_history(self):
        if not self._check_pin("effacer l'historique long terme"):
            return
        reply = QMessageBox.question(
            self, "Confirmer l'effacement",
            "Effacer definitivement tout l'historique SOH long terme (toutes sessions) ?\n\n"
            "Cette action est irreversible.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.history_store.clear_all()
        self._refresh_longterm_chart()
        self._log("Historique long terme efface")

    def _refresh_longterm_chart(self):
        rows = self.history_store.get_history(limit=2000)
        if len(rows) < 2:
            self.longterm_stats_lbl.setText(
                "Historique en cours de constitution... (un point est enregistre toutes les 5 ticks)"
            )
            self.longterm_curve.setData([], [])
            return

        timestamps = [datetime.fromisoformat(r[0]) for r in rows]
        sohs = [r[1] for r in rows]
        t0 = timestamps[0]
        x_minutes = [(t - t0).total_seconds() / 60.0 for t in timestamps]
        self.longterm_curve.setData(x_minutes, sohs)

        n_sessions = self.history_store.count_sessions()
        span = timestamps[-1] - timestamps[0]
        span_txt = f"{span.days}j {span.seconds // 3600}h" if span.days > 0 else f"{span.seconds // 3600}h{(span.seconds % 3600)//60:02d}"
        self.longterm_stats_lbl.setText(
            f"{len(rows)} points sur {n_sessions} session(s)  |  "
            f"periode couverte : {span_txt}  |  SOH actuel : {sohs[-1]:.2f}%"
        )

    def _reset_bms(self):
        if not self._check_pin("reinitialiser le BMS (RAZ compteurs/session)"):
            return
        reply = QMessageBox.question(
            self, "Confirmer Reset BMS",
            "Reinitialiser tous les compteurs de protection, le compteur de cycles, "
            "la session et l'historique CSV ?\n\n"
            "Les seuils de protection et la chimie selectionnee sont conserves.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        for key in self.protection_events:
            self.protection_events[key] = 0
            self._event_flags[key] = False
            self.event_labels[key].setText("0")
        self.battery_cycles = 0
        self._cycle_armed_low = False
        self.settings.setValue("session/battery_cycles", 0)
        self.cycles_lbl.setText("0")
        self._reset_session()
        self.full_history = []
        self.log_list.clear()
        self._update_alarm_badge()
        self._log("RAZ complete du BMS effectuee (PIN valide)")
        QMessageBox.information(self, "Reset BMS", "Reinitialisation terminee.")

    def _close_bms(self):
        if not self._check_pin("fermer le BMS (coupure Charge + Discharge)"):
            return
        reply = QMessageBox.question(
            self, "Confirmer Close BMS",
            "Couper immediatement les relais Charge et Discharge (isolation complete du pack) ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.charge_enabled = False
        self.discharge_enabled = False
        self.charge_toggle.setChecked(False)
        self.charge_toggle.setText("Charge : OFF")
        self.charge_toggle.setStyleSheet(self._toggle_style(False))
        self.discharge_toggle.setChecked(False)
        self.discharge_toggle.setText("Discharge : OFF")
        self.discharge_toggle.setStyleSheet(self._toggle_style(False))
        self.settings.setValue("relay/charge_enabled", False)
        self.settings.setValue("relay/discharge_enabled", False)
        self._log("BMS ferme : Charge et Discharge coupes (isolation pack)")
        QMessageBox.information(self, "BMS ferme", "Le pack est isole (Charge et Discharge desactives).")

    def _reset_factory_settings(self):
        if not self._check_pin("reinitialiser les parametres d'usine"):
            return
        reply = QMessageBox.question(
            self, "Confirmer Reset Factory Settings",
            "ATTENTION : reinitialise TOUS les parametres (seuils, chimie, PIN, relais, "
            "compteurs) aux valeurs d'usine.\n\nCette action est irreversible. Continuer ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.settings.clear()
        self.settings.sync()

        # Chimie -> Li-ion (reutilise la logique deja testee de _set_chemistry)
        self._set_chemistry("liion")

        # Seuils non lies a la tension (non couverts par _set_chemistry)
        NONVOLTAGE_DEFAULTS = {
            "charge_overcurrent": 30.0, "discharge_overcurrent": 50.0,
            "short_circuit_current": 80.0, "charge_over_temperature": 50.0,
            "discharge_over_temperature": 55.0, "balancing_precision": 0.03,
        }
        for key, value in NONVOLTAGE_DEFAULTS.items():
            self.protection_params[key] = value
            self.settings.setValue(f"protection/{key}", value)
            if key in self.param_spinboxes:
                self.param_spinboxes[key].setValue(value)

        # PIN, relais
        self.pin_hash = DEFAULT_PIN_HASH
        for enabled_attr, toggle, settings_key, label_prefix in [
            ("charge_enabled", self.charge_toggle, "relay/charge_enabled", "Charge"),
            ("discharge_enabled", self.discharge_toggle, "relay/discharge_enabled", "Discharge"),
            ("autobalance_enabled", self.autobalance_toggle, "relay/autobalance_enabled", "AutoBalance"),
        ]:
            setattr(self, enabled_attr, True)
            toggle.setChecked(True)
            toggle.setText(f"{label_prefix} : ON")
            toggle.setStyleSheet(self._toggle_style(True))
            self.settings.setValue(settings_key, True)
        self.sim.set_autobalance(True)

        # RAZ complete (compteurs, cycles, session, historique, journal)
        for key in self.protection_events:
            self.protection_events[key] = 0
            self._event_flags[key] = False
            self.event_labels[key].setText("0")
        self.battery_cycles = 0
        self._cycle_armed_low = False
        self.cycles_lbl.setText("0")
        self._reset_session()
        self.full_history = []
        self.log_list.clear()
        self._update_alarm_badge()

        self._log("RAZ USINE effectuee : configuration entierement reinitialisee")
        QMessageBox.information(self, "Reset usine", "Tous les parametres ont ete reinitialises aux valeurs d'usine.")

    def _update_session_stats(self, pack_v, current):
        if self.session_min_v is None or pack_v < self.session_min_v:
            self.session_min_v = pack_v
        if self.session_max_v is None or pack_v > self.session_max_v:
            self.session_max_v = pack_v
        power_w = abs(current) * pack_v
        if current < 0:
            self.session_max_charge_p = max(self.session_max_charge_p, power_w)
        elif current > 0:
            self.session_max_discharge_p = max(self.session_max_discharge_p, power_w)

        duration = datetime.now() - self.session_start
        mins, secs = divmod(int(duration.total_seconds()), 60)
        hours, mins = divmod(mins, 60)
        self.session_labels["min_v"].setText(f"{self.session_min_v:.2f} V")
        self.session_labels["max_v"].setText(f"{self.session_max_v:.2f} V")
        self.session_labels["max_charge_p"].setText(f"{self.session_max_charge_p:.0f} W")
        self.session_labels["max_discharge_p"].setText(f"{self.session_max_discharge_p:.0f} W")
        self.session_labels["duration"].setText(f"{hours:02d}:{mins:02d}:{secs:02d}")

    def _check_protection_events(self, voltages, current, temp):
        """Detection a front montant : incremente le compteur une seule fois par
        depassement de seuil (pas a chaque tick tant que la condition reste vraie),
        et se reinitialise quand la valeur repasse sous le seuil de relachement."""
        p = self.protection_params

        def trigger(key, active_now, release_now):
            if active_now and not self._event_flags[key]:
                self.protection_events[key] += 1
                self.event_labels[key].setText(str(self.protection_events[key]))
                self._event_flags[key] = True
                self._log(f"Declenchement protection: {key}")
                self._update_alarm_badge()
            elif release_now:
                self._event_flags[key] = False

        v_max = max(voltages)
        v_min = min(voltages)
        trigger("cell_overvoltage", v_max >= p["overvoltage"], v_max < p["overvoltage_release"])
        trigger("cell_undervoltage", v_min <= p["undervoltage"], v_min > p["undervoltage_release"])

        # Charge (current < 0) vs decharge (current > 0) : seuils et compteurs separes,
        # comme sur les BMS commerciaux (SZLLT / ANT BMS)
        trigger("charge_overcurrent", current < 0 and abs(current) >= p["charge_overcurrent"],
                not (current < 0 and abs(current) >= p["charge_overcurrent"] * 0.9))
        trigger("discharge_overcurrent", current > 0 and current >= p["discharge_overcurrent"],
                not (current > 0 and current >= p["discharge_overcurrent"] * 0.9))
        trigger("charge_over_temperature",
                current < 0 and temp >= p["charge_over_temperature"],
                temp < p["charge_over_temperature"] - 3)
        trigger("discharge_over_temperature",
                current > 0 and temp >= p["discharge_over_temperature"],
                temp < p["discharge_over_temperature"] - 3)
        trigger("short_circuit", abs(current) >= p["short_circuit_current"],
                abs(current) < p["short_circuit_current"] * 0.5)

    def _check_battery_cycles(self, soc):
        """Approxime un cycle de charge/decharge complet (comme le compteur 'Battery cycles'
        des BMS commerciaux) : arme quand le SOC descend sous 20%, valide le cycle quand
        il remonte au-dessus de 80%."""
        if soc <= 20:
            self._cycle_armed_low = True
        elif soc >= 80 and self._cycle_armed_low:
            self.battery_cycles += 1
            self._cycle_armed_low = False
            self.settings.setValue("session/battery_cycles", self.battery_cycles)
            if hasattr(self, "cycles_lbl"):
                self.cycles_lbl.setText(str(self.battery_cycles))
            self._log(f"Cycle de charge/decharge complete (total: {self.battery_cycles})")

    def _update_rul_estimate(self):
        """Regression lineaire sur l'historique SOH/tick pour estimer le RUL (Remaining
        Useful Life) : dans combien de temps/cycles le SOH franchira le seuil de fin
        de vie (80%, standard couramment utilise pour les batteries Li-ion)."""
        EOL_THRESHOLD = 80.0
        history = self.soh_history
        if len(history) < 10:
            self.soh_trend_lbl.setText("Tendance : collecte de donnees en cours...")
            return

        ticks = np.array([t for t, _ in history], dtype=float)
        sohs = np.array([s for _, s in history], dtype=float)
        slope, intercept = np.polyfit(ticks, sohs, 1)

        predicted = slope * ticks + intercept
        ss_res = np.sum((sohs - predicted) ** 2)
        ss_tot = np.sum((sohs - np.mean(sohs)) ** 2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        current_soh = sohs[-1]
        current_tick = ticks[-1]
        self.rul_curve.setData(ticks, sohs)

        if current_soh <= EOL_THRESHOLD:
            self.rul_projection_curve.setData([], [])
            self.rul_stats_lbl.setText(
                f"Seuil de fin de vie ({EOL_THRESHOLD:.0f}%) deja atteint. SOH actuel : {current_soh:.2f}%"
            )
            self.soh_trend_lbl.setText("RUL : seuil de fin de vie atteint")
        elif slope < -1e-6:
            ticks_to_eol = (EOL_THRESHOLD - current_soh) / slope
            eol_tick = current_tick + ticks_to_eol
            self.rul_projection_curve.setData(
                np.array([current_tick, eol_tick]), np.array([current_soh, EOL_THRESHOLD])
            )

            cycles_per_tick = self.battery_cycles / max(1, self.tick)
            if cycles_per_tick > 0:
                cycles_txt = f"~{ticks_to_eol * cycles_per_tick:.0f} cycles"
            else:
                cycles_txt = "cycles non mesurables (aucun cycle complet observe)"

            minutes_remaining = ticks_to_eol / 60.0
            confidence = "haute" if r_squared > 0.7 else ("moyenne" if r_squared > 0.3 else "faible")
            self.rul_stats_lbl.setText(
                f"Pente : {slope*3600:.3f} %/h simulee  |  RUL estime : {cycles_txt}\n"
                f"(~{minutes_remaining:.0f} min avant seuil {EOL_THRESHOLD:.0f}%)  |  "
                f"Fiabilite : {confidence} (R2={r_squared:.2f}, {len(history)} points)"
            )
            self.soh_trend_lbl.setText(f"RUL : {cycles_txt} avant seuil {EOL_THRESHOLD:.0f}%")
        else:
            self.rul_projection_curve.setData([], [])
            self.rul_stats_lbl.setText(
                f"SOH stable (pente={slope*3600:.4f} %/h) -- pas de degradation nette detectee."
            )
            self.soh_trend_lbl.setText("Tendance : stable")

    def _step(self):
        self.tick += 1
        reading = self.sim.step()
        self.buffer.append(reading)

        # Flotte : avance chaque pack independamment et rafraichit sa carte
        for pack in self.fleet:
            data = pack.step()
            self.fleet_cards[pack.name].update_data(data)

        voltages = reading["cell_v"]
        balancing_indices = reading.get("balancing_indices", [])
        current = reading["current_a"]
        temp = reading["temp_c"]

        # Relais Charge/Discharge : coupe le courant affiche/utilise en aval si desactive
        # (simplification pedagogique : les tensions cellule restent celles du simulateur physique,
        # seul le courant "vu par le systeme" est coupe, comme le ferait un MOSFET de protection).
        if current < 0 and not self.charge_enabled:
            current = 0.0
        if current > 0 and not self.discharge_enabled:
            current = 0.0

        pack_v = sum(voltages)
        imbalance = max(voltages) - min(voltages)
        soc = self.sim.cells[0].soc * 100
        soh = reading["soh"]

        self.card_voltage.set_value(f"{pack_v:.1f}", GREEN)
        self.card_current.set_value(f"{current:.1f}", "#7CC3F5" if current < 0 else TEXT)
        temp_color = "#FF5C4D" if temp > 55 else ("#F5B942" if temp > 40 else TEXT)
        self.card_temp.set_value(f"{temp:.0f}", temp_color)
        self.card_imbalance.set_value(f"{imbalance:.2f}", "#F5B942" if imbalance > 0.12 else TEXT)
        self._check_protection_events(voltages, current, temp)
        self._check_battery_cycles(soc)
        self._update_session_stats(pack_v, current)
        self.soc_gauge.set_value(soc)
        self.soc_gauge.set_subtitle(f"{self.sim.cells[0].capacity_ah * soc / 100:.2f} AH restant")
        self.soh_gauge.set_value(soh)
        self.soh_gauge.set_subtitle(f"Tick {self.tick}")

        # RUL (Remaining Useful Life) : regression lineaire sur l'historique SOH/tick
        self.soh_history.append((self.tick, soh))
        self._update_rul_estimate()

        # Historique long terme (persiste entre sessions) : un point toutes les 5 ticks
        # suffit largement (evite d'ecrire sur disque a chaque seconde simulee)
        if self.tick % 5 == 0:
            self.history_store.insert_point(self.tick, self.battery_cycles, soh, soc, self.sim.scenario)
            self._refresh_longterm_chart()

        fault_index = None
        scenario = self.sim.scenario
        from battery_model import FAULT_CELL_IMBALANCE, FAULT_CELL_RESISTANCE, FAULT_CELL_OVERVOLT
        if scenario == "desequilibre":
            fault_index = FAULT_CELL_IMBALANCE
        elif scenario == "resistance":
            fault_index = FAULT_CELL_RESISTANCE
        elif scenario == "surtension" and voltages[FAULT_CELL_OVERVOLT] > 4.15:
            fault_index = FAULT_CELL_OVERVOLT
        self.cell_bank.set_data(voltages, fault_index, SCENARIOS[scenario]["color"], balancing_indices)
        if self.autobalance_enabled:
            self.balancing_lbl.setText(f"Cellules en equilibrage : {len(balancing_indices)}")
        delta_color = "#FF5C4D" if imbalance > 0.08 else MUTED
        self.cell_delta_lbl.setText(f"delta V: {imbalance:.3f}")
        self.cell_delta_lbl.setStyleSheet(f"color:{delta_color}; font-family:Consolas; font-size:10px; font-weight:bold; border:none;")

        self.history_v.append(sum(voltages) / NUM_CELLS * 10)
        self.history_i.append(current)
        self.history_temp.append(temp)
        self.curve_v.setData(list(self.history_v))
        self.curve_i.setData(list(self.history_i))

        self.last_snapshot = {
            "pack_v": pack_v, "current": current, "temp": temp,
            "soc": soc, "soh": soh, "cell_voltages": list(voltages),
            "fault_index": fault_index,
        }
        self.full_history.append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "tick": self.tick, "pack_v": pack_v, "current": current, "temp": temp,
            "soc": soc, "soh": soh, "scenario": scenario,
            **{f"cell_{i+1}_v": v for i, v in enumerate(voltages)},
        })

        if len(self.buffer) >= 10:
            self._run_diagnosis()
        self._update_risk_status()

    def _run_diagnosis(self):
        features = extract_features(list(self.buffer))
        x = np.array([[features[c] for c in FEATURE_ORDER]])
        x_scaled = self.scaler.transform(x)
        pred = self.rf_model.predict(x_scaled)[0]
        proba = self.rf_model.predict_proba(x_scaled)[0]
        classes = list(self.rf_model.classes_)

        self.last_label = pred
        self.last_confidence = float(max(proba))
        self.last_probabilities = {cls: float(p) for cls, p in zip(classes, proba)}

        for label, bar in self.proba_bars.items():
            pct = int(round(self.last_probabilities.get(label, 0.0) * 100))
            bar.setValue(pct)

        self._update_explainability(x_scaled[0])

    def _update_explainability(self, z_scores):
        """Explicabilite 'pauvre-homme' du diagnostic : combine l'importance globale
        du Random Forest (feature_importances_, fixe) avec l'ecart-type local de chaque
        variable par rapport a la moyenne d'entrainement (x_scaled = z-score, deja calcule
        par le StandardScaler). Le produit approxime quelles variables pesent le plus dans
        LE DIAGNOSTIC ACTUEL -- ce n'est pas une vraie valeur SHAP, mais ca reste honnete
        et bien plus informatif qu'un pourcentage de confiance seul."""
        importances = self.rf_model.feature_importances_
        impact = importances * np.abs(z_scores)
        total = impact.sum()
        if total <= 0:
            return
        pct_by_feature = {feat: 100.0 * impact[i] / total for i, feat in enumerate(FEATURE_ORDER)}

        for feat, bar in self.explain_bars.items():
            bar.setValue(int(round(pct_by_feature[feat])))

        top3 = sorted(pct_by_feature.items(), key=lambda kv: kv[1], reverse=True)[:3]
        parts = [f"{self.FEATURE_LABELS.get(feat, feat)} ({pct:.0f}%)" for feat, pct in top3 if pct > 1]
        if parts:
            self.explain_sentence.setText("Diagnostic influence surtout par : " + ", ".join(parts) + ".")
        else:
            self.explain_sentence.setText("Toutes les variables sont proches de leur valeur normale.")

    def _update_risk_status(self):
        """Combine la prediction du modele et une tendance (temperature/desequilibre) pour
        afficher un etat 'SURVEILLANCE' AVANT que le modele confirme un defaut avec certitude —
        c'est ce qui rend le tableau de bord predictif, pas seulement reactif."""
        reverse_map = {v: k for k, v in SCENARIO_TO_MODEL_LABEL.items()}
        demo_key = reverse_map.get(self.last_label, "normal")
        info = SCENARIOS[demo_key]

        temp_slope = 0.0
        if len(self.history_temp) >= 10:
            temp_slope = (self.history_temp[-1] - self.history_temp[-10]) / 10.0
        imbalance = 0.0
        if self.last_snapshot:
            v = self.last_snapshot["cell_voltages"]
            imbalance = max(v) - min(v)

        if self.last_label != "normal" and self.last_confidence >= 0.55:
            risk, pill_text, pill_color = demo_key, info["label"].upper(), info["color"]
            self.diag_label.setText(info["label"])
            self.diag_desc.setText(info["desc"])
        elif temp_slope > 0.3 or imbalance > 0.08:
            risk = "surveillance"
            pill_text, pill_color = "SURVEILLANCE — tendance anormale", "#F5B942"
            self.diag_label.setText("Surveillance renforcee")
            self.diag_desc.setText(
                "Aucun defaut confirme, mais une tendance (temperature ou desequilibre) "
                "s'ecarte de la normale. A surveiller."
            )
        else:
            risk = "normal"
            pill_text, pill_color = "NORMAL", GREEN
            self.diag_label.setText(info["label"])
            self.diag_desc.setText(info["desc"])

        self.risk_level = risk
        self.diag_label.setStyleSheet(f"color:{pill_color}; font-family:Consolas; font-size:14px; border:none;")
        self.diag_conf.setText(f"Confiance : {self.last_confidence*100:.0f}%  |  Pente temp. : {temp_slope:+.2f} C/s")

        self.status_pill.setText(pill_text)
        self.status_pill.setStyleSheet(
            f"background:{pill_color}22; color:{pill_color}; border:1px solid {pill_color}; "
            "border-radius:14px; padding:6px 16px; font-family:Consolas; font-size:12px;"
        )

    def _export_pdf(self):
        if not self.last_snapshot or not self.last_probabilities:
            QMessageBox.information(self, "Rapport", "Pas encore assez de donnees pour generer un rapport. Patiente quelques secondes.")
            return

        default_name = f"rapport_bms_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Exporter le diagnostic", default_name, "PDF (*.pdf)")
        if not path:
            return

        try:
            import report_generator
            snapshot = dict(self.last_snapshot)
            snapshot["label"] = self.last_label
            snapshot["confidence"] = self.last_confidence
            snapshot["probabilities"] = self.last_probabilities
            report_generator.generate_pdf_report(path, snapshot)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de generer le rapport :\n{e}")
            return

        self._log(f"Rapport PDF exporte -> {os.path.basename(path)}")
        reply = QMessageBox.information(
            self, "Rapport genere", f"Rapport enregistre :\n{path}\n\nOuvrir maintenant ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                os.startfile(path)  # Windows
            except AttributeError:
                import subprocess
                subprocess.Popen(["xdg-open", path])

    def _export_full_report(self):
        if not self.last_snapshot or not self.last_probabilities:
            QMessageBox.information(self, "Rapport", "Pas encore assez de donnees pour generer un rapport. Patiente quelques secondes.")
            return

        default_name = f"rapport_complet_bms_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Exporter le rapport complet", default_name, "PDF (*.pdf)")
        if not path:
            return

        try:
            import report_generator
            snapshot = dict(self.last_snapshot)
            snapshot["label"] = self.last_label
            snapshot["confidence"] = self.last_confidence
            snapshot["probabilities"] = self.last_probabilities

            session_data = {
                "Tension min": self.session_labels["min_v"].text(),
                "Tension max": self.session_labels["max_v"].text(),
                "Puissance max charge": self.session_labels["max_charge_p"].text(),
                "Puissance max decharge": self.session_labels["max_discharge_p"].text(),
                "Duree session": self.session_labels["duration"].text(),
            }
            device_info = {
                "Fabricant": "Akkurad GmbH",
                "Modele": "Smart BMS — Simulateur",
                "Config. pack": self.pack_config_lbl.text() if hasattr(self, "pack_config_lbl") else "10S",
                "Capacite nominale": f"{self.sim.cells[0].capacity_ah:.1f} AH",
                "Cycles": str(self.battery_cycles),
            }
            log_entries = [self.log_list.item(i).text() for i in range(self.log_list.count())]

            report_generator.generate_full_report(
                path, snapshot,
                soh_history=list(self.soh_history),
                protection_events=dict(self.protection_events),
                session_data=session_data,
                device_info=device_info,
                log_entries=log_entries,
            )
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de generer le rapport complet :\n{e}")
            return

        self._log(f"Rapport complet (3 pages) exporte -> {os.path.basename(path)}")
        reply = QMessageBox.information(
            self, "Rapport genere", f"Rapport complet (3 pages) enregistre :\n{path}\n\nOuvrir maintenant ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                os.startfile(path)  # Windows
            except AttributeError:
                import subprocess
                subprocess.Popen(["xdg-open", path])

    def _export_csv(self):
        if not self.full_history:
            QMessageBox.information(self, "Export CSV", "Pas encore de donnees a exporter.")
            return

        default_name = f"bms_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Exporter les donnees brutes", default_name, "CSV (*.csv)")
        if not path:
            return

        try:
            fieldnames = list(self.full_history[0].keys())
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.full_history)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'exporter le CSV :\n{e}")
            return

        self._log(f"Donnees CSV exportees -> {os.path.basename(path)} ({len(self.full_history)} lignes)")
        QMessageBox.information(self, "Export termine", f"{len(self.full_history)} lignes enregistrees dans :\n{path}")

    def _refresh_recordings_list(self):
        self.recordings_list.clear()
        for label, path in self.recording_store.list_recordings():
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, str(path))
            self.recordings_list.addItem(item)

    def _save_recording(self):
        if not self.full_history:
            QMessageBox.information(self, "Enregistrer", "Pas encore de donnees a enregistrer.")
            return
        name, ok = QInputDialog.getText(
            self, "Enregistrer ce scenario",
            "Nom de l'enregistrement :", QLineEdit.Normal,
            f"{self.sim.scenario}_{datetime.now().strftime('%H%M%S')}",
        )
        if not ok or not name.strip():
            return
        path = self.recording_store.save(name.strip(), self.full_history)
        self._refresh_recordings_list()
        self._log(f"Scenario enregistre : {name.strip()} ({len(self.full_history)} points)")
        QMessageBox.information(self, "Enregistre", f"Scenario sauvegarde :\n{path.name}")

    def _selected_recording_paths(self):
        return [Path(item.data(Qt.UserRole)) for item in self.recordings_list.selectedItems()]

    def _replay_selected_recording(self):
        paths = self._selected_recording_paths()
        if len(paths) != 1:
            QMessageBox.information(self, "Rejouer", "Selectionne exactement UN enregistrement a rejouer.")
            return
        rows = self.recording_store.load(paths[0])
        if not rows:
            QMessageBox.warning(self, "Rejouer", "Cet enregistrement est vide.")
            return
        dlg = ReplayDialog(paths[0].stem, rows, self)
        dlg.exec()

    def _compare_selected_recordings(self):
        paths = self._selected_recording_paths()
        if len(paths) != 2:
            QMessageBox.information(self, "Comparer", "Selectionne exactement DEUX enregistrements a comparer (Ctrl+clic).")
            return
        rows_a = self.recording_store.load(paths[0])
        rows_b = self.recording_store.load(paths[1])
        if not rows_a or not rows_b:
            QMessageBox.warning(self, "Comparer", "Un des deux enregistrements est vide.")
            return
        dlg = ComparisonDialog(paths[0].stem, rows_a, paths[1].stem, rows_b, self)
        dlg.exec()

    def _delete_selected_recordings(self):
        paths = self._selected_recording_paths()
        if not paths:
            QMessageBox.information(self, "Supprimer", "Selectionne au moins un enregistrement.")
            return
        reply = QMessageBox.question(
            self, "Confirmer la suppression",
            f"Supprimer {len(paths)} enregistrement(s) ? Cette action est irreversible.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        for p in paths:
            self.recording_store.delete(p)
        self._refresh_recordings_list()
        self._log(f"{len(paths)} enregistrement(s) supprime(s)")


def _build_splash_pixmap():
    """Construit le pixmap du splash screen (theme sombre coherent avec le dashboard)."""
    w, h = 480, 280
    pix = QPixmap(w, h)
    pix.fill(QColor(BG))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    painter.setPen(QPen(QColor(BORDER), 2))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(1, 1, w - 2, h - 2, 16, 16)

    if ICON_PATH.exists():
        icon_pix = QPixmap(str(ICON_PATH)).scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        painter.drawPixmap((w - 72) // 2, 34, icon_pix)

    painter.setPen(QColor(TEXT))
    painter.setFont(QFont("Segoe UI", 20, QFont.Bold))
    painter.drawText(0, 118, w, 36, Qt.AlignCenter, "Smart BMS")

    painter.setPen(QColor(COPPER))
    painter.setFont(QFont("Segoe UI", 10))
    painter.drawText(0, 154, w, 20, Qt.AlignCenter, "Akkurad GmbH  —  Diagnostic predictif pack LiPo")

    painter.setPen(QColor(DIM))
    painter.setFont(QFont("Consolas", 8))
    painter.drawText(w - 148, 10, 136, 14, Qt.AlignRight, f"v{APP_VERSION}  ({APP_BUILD_DATE})")

    painter.end()
    return pix


class AboutDialog(QDialog):
    """Fenetre 'A propos' : version, date de build, contact -- accessible depuis l'en-tete."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("A propos de Smart BMS")
        self.setFixedSize(360, 280)
        self.setStyleSheet(f"background:{BG}; color:{TEXT};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(6)

        if ICON_PATH.exists():
            icon_lbl = QLabel()
            icon_lbl.setPixmap(QPixmap(str(ICON_PATH)).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            icon_lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(icon_lbl)

        title = QLabel("Smart BMS")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color:{TEXT}; font-family:'Segoe UI'; font-size:16px; font-weight:bold; border:none;")
        layout.addWidget(title)

        subtitle = QLabel("Diagnostic predictif — pack LiPo micro-mobilite electrique")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color:{COPPER}; font-size:10px; border:none;")
        layout.addWidget(subtitle)

        layout.addSpacing(10)
        for label, value in [
            ("Version", APP_VERSION),
            ("Date de build", APP_BUILD_DATE),
            ("Developpe pour", "Akkurad GmbH"),
            ("Contact", "stage@akkurad.example"),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{MUTED}; font-size:10px; border:none;")
            val = QLabel(value)
            val.setStyleSheet(f"color:{TEXT}; font-family:Consolas; font-size:10px; border:none;")
            val.setAlignment(Qt.AlignRight)
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            layout.addLayout(row)

        layout.addStretch()
        close_btn = QPushButton("Fermer")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background:{COPPER}; color:#141414; border:none; border-radius:6px;
                padding:8px; font-family:Consolas; font-size:10px; font-weight:bold;
            }}
            QPushButton:hover {{ background:#E8A159; }}
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class LegendDialog(QDialog):
    """Explique les codes couleur et symboles utilises dans tout le dashboard --
    evite toute question en soutenance sur 'pourquoi cette bordure est bleue'."""

    ENTRIES = [
        ("battery", GREEN, "Cellule en etat normal"),
        ("battery", "#F5B942", "Cellule proche d'un seuil (surveillance)"),
        ("battery", "#FF5C4D", "Cellule hors seuil (defaut confirme)"),
        ("info", "#7CC3F5", "Borne bleue = cellule a la tension la plus haute (Vmax)"),
        ("info", "#B388FF", "Borne violette = cellule a la tension la plus basse (Vmin)"),
        ("refresh-cw", "#F5B942", "Anneau ambre = cellule en cours d'equilibrage (AutoBalance)"),
        ("check-circle", GREEN, "Badge NORMAL : aucune anomalie detectee"),
        ("alert-triangle", "#F5B942", "Badge SURVEILLANCE : tendance anormale, pas encore confirmee"),
        ("alert-triangle", "#FF5C4D", "Badge ALARME : defaut confirme, action requise"),
        ("trending-down", COPPER, "Courbe pleine = SOH mesure ; pointilles ambres = projection RUL"),
        ("trending-down", "#FF5C4D", "Ligne rouge pointillee = seuil de fin de vie (80% SOH)"),
        ("lock", MUTED, "Action protegee par code PIN (seuils, chimie, maintenance)"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Legende")
        self.setMinimumSize(420, 440)
        self.setStyleSheet(f"background:{BG}; color:{TEXT};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title = IconLabel("help-circle", "Legende des couleurs et symboles", color=TEXT, size=14, bold=True)
        layout.addWidget(title)

        for icon_name, color, text in self.ENTRIES:
            row = QHBoxLayout()
            icon_lbl = QLabel()
            icon_lbl.setPixmap(icon_pixmap(icon_name, color, 16, bg=BG))
            icon_lbl.setStyleSheet("background:transparent; border:none;")
            icon_lbl.setFixedWidth(24)
            row.addWidget(icon_lbl)
            text_lbl = QLabel(text)
            text_lbl.setWordWrap(True)
            text_lbl.setStyleSheet(f"color:{MUTED}; font-size:10px; border:none;")
            row.addWidget(text_lbl, stretch=1)
            layout.addLayout(row)

        layout.addStretch()
        close_btn = QPushButton("Fermer")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background:{COPPER}; color:#141414; border:none; border-radius:6px;
                padding:8px; font-family:Consolas; font-size:10px; font-weight:bold;
            }}
            QPushButton:hover {{ background:#E8A159; }}
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class ReplayDialog(QDialog):
    """Rejoue une sequence enregistree : banc de cellules + curseur pour se deplacer
    dans le temps, ou lecture automatique. Fonctionne sur les donnees deja enregistrees,
    independamment de la simulation live du dashboard principal."""

    def __init__(self, name, rows, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.setWindowTitle(f"Rejeu — {name}")
        self.setMinimumSize(520, 480)
        self.setStyleSheet(f"background:{BG}; color:{TEXT};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)

        title = IconLabel("play", name, color=TEXT, size=14, bold=True)
        layout.addWidget(title)

        self.info_lbl = QLabel("")
        self.info_lbl.setWordWrap(True)
        self.info_lbl.setStyleSheet(f"color:{MUTED}; font-family:Consolas; font-size:11px; border:none;")
        layout.addWidget(self.info_lbl)

        cell_frame = QFrame()
        cell_frame.setStyleSheet(f"background:{SURFACE}; border:1px solid {BORDER}; border-radius:8px;")
        cell_layout = QVBoxLayout(cell_frame)
        self.cell_bank = CellBankWidget()
        cell_layout.addWidget(self.cell_bank)
        layout.addWidget(cell_frame)

        controls = QHBoxLayout()
        self.play_btn = QPushButton()
        set_button_icon(self.play_btn, "play", TEXT, size=14, bg=SURFACE)
        self.play_btn.setFixedSize(36, 36)
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.setStyleSheet(f"QPushButton {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:18px; }}")
        self.play_btn.clicked.connect(self._toggle_play)
        controls.addWidget(self.play_btn)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, max(0, len(rows) - 1))
        self.slider.valueChanged.connect(self._show_frame)
        controls.addWidget(self.slider, stretch=1)
        layout.addLayout(controls)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance)
        self.playing = False

        if rows:
            self._show_frame(0)

    def _toggle_play(self):
        self.playing = not self.playing
        set_button_icon(self.play_btn, "pause" if self.playing else "play", TEXT, size=14, bg=SURFACE)
        if self.playing:
            self.timer.start(150)  # lecture acceleree (pas 1:1 avec le tick reel)
        else:
            self.timer.stop()

    def _advance(self):
        next_val = self.slider.value() + 1
        if next_val > self.slider.maximum():
            self._toggle_play()
            return
        self.slider.setValue(next_val)

    def _show_frame(self, idx):
        if not self.rows:
            return
        row = self.rows[idx]
        voltages = [row.get(f"cell_{i+1}_v", 3.75) for i in range(NUM_CELLS)]
        self.cell_bank.set_data(voltages, None, GREEN)
        self.info_lbl.setText(
            f"Tick {row.get('tick', idx)}  |  Scenario: {row.get('scenario', '?')}  |  "
            f"SOC: {row.get('soc', 0):.1f}%  |  SOH: {row.get('soh', 0):.1f}%  |  "
            f"Pack: {row.get('pack_v', 0):.2f}V  |  Temp: {row.get('temp', 0):.1f}C  |  "
            f"({idx+1}/{len(self.rows)})"
        )


class ComparisonDialog(QDialog):
    """Superpose une metrique au choix (SOH, tension pack, temperature, courant) de
    deux enregistrements sur un meme graphique, pour comparer visuellement deux runs."""

    METRICS = {
        "soh": "SOH (%)", "pack_v": "Tension pack (V)",
        "temp": "Temperature (C)", "current": "Courant (A)",
    }

    def __init__(self, name_a, rows_a, name_b, rows_b, parent=None):
        super().__init__(parent)
        self.rows_a, self.rows_b = rows_a, rows_b
        self.name_a, self.name_b = name_a, name_b
        self.setWindowTitle(f"Comparaison — {name_a} vs {name_b}")
        self.setMinimumSize(560, 420)
        self.setStyleSheet(f"background:{BG}; color:{TEXT};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)

        title = IconLabel("layers", f"{name_a}  vs  {name_b}", color=TEXT, size=13, bold=True)
        layout.addWidget(title)

        self.metric_combo = QComboBox()
        for key, label in self.METRICS.items():
            self.metric_combo.addItem(label, key)
        self.metric_combo.setStyleSheet(
            f"QComboBox {{ background:{SURFACE}; color:{TEXT}; border:1px solid {BORDER}; "
            "border-radius:4px; padding:4px; font-family:Consolas; font-size:10px; }"
        )
        self.metric_combo.currentIndexChanged.connect(self._redraw)
        layout.addWidget(self.metric_combo)

        pg.setConfigOption("background", SURFACE)
        pg.setConfigOption("foreground", MUTED)
        self.plot = pg.PlotWidget()
        self.plot.addLegend()
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        self.curve_a = self.plot.plot(pen=pg.mkPen(COPPER, width=2), name=name_a)
        self.curve_b = self.plot.plot(pen=pg.mkPen("#7CC3F5", width=2), name=name_b)
        layout.addWidget(self.plot)

        self._redraw()

    def _redraw(self):
        metric = self.metric_combo.currentData()
        xa = [r.get("tick", i) for i, r in enumerate(self.rows_a)]
        ya = [r.get(metric, 0) for r in self.rows_a]
        xb = [r.get("tick", i) for i, r in enumerate(self.rows_b)]
        yb = [r.get(metric, 0) for r in self.rows_b]
        self.curve_a.setData(xa, ya)
        self.curve_b.setData(xb, yb)
        self.plot.getAxis("left").setLabel(self.METRICS[metric])
        self.plot.getAxis("bottom").setLabel("tick")


def main():
    app = QApplication(sys.argv)
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))

    splash = QSplashScreen(_build_splash_pixmap(), Qt.WindowStaysOnTopHint)
    splash.setWindowFlag(Qt.FramelessWindowHint)
    splash.show()
    splash.showMessage("Chargement du modele de diagnostic (Random Forest)...",
                        Qt.AlignBottom | Qt.AlignHCenter, QColor(MUTED))
    app.processEvents()

    win = MainWindow()

    splash.showMessage("Interface prete.", Qt.AlignBottom | Qt.AlignHCenter, QColor(MUTED))
    app.processEvents()

    win.show()
    splash.finish(win)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
