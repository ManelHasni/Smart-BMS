"""
CellVoltageGrid - Grille de tensions cellule par cellule avec code couleur
Inspiré des apps BMS commerciales (Xiaoxiang / JBD BMS)

Chaque cellule s'affiche comme un petit "bloc batterie":
- Vert  : tension normale
- Orange: proche d'un seuil (warning)
- Rouge : hors seuil (critique) -> fault
- Bordure bleue: cellule la plus haute (Vmax)
- Bordure violette: cellule la plus basse (Vmin)
- Petit point clignotant: cellule en cours d'équilibrage (balancing)

Adapté à un pack 10S/36V LiPo (Akkurad).
"""

from PySide6.QtWidgets import QWidget, QGridLayout, QLabel, QVBoxLayout, QFrame, QSizePolicy
from PySide6.QtGui import QColor, QFont
from PySide6.QtCore import Qt


class CellCard(QFrame):
    """Un seul bloc de cellule (numéro + tension), colorisé selon l'état."""

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumSize(78, 54)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(1)

        top_row = QLabel(f"#{index}")
        top_row.setAlignment(Qt.AlignLeft)
        top_row.setFont(QFont("Segoe UI", 8))
        top_row.setStyleSheet("color: #555; background: transparent;")

        self.value_label = QLabel("--.-- V")
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.value_label.setStyleSheet("background: transparent;")

        self.flag_label = QLabel("")
        self.flag_label.setAlignment(Qt.AlignRight)
        self.flag_label.setFont(QFont("Segoe UI", 8))
        self.flag_label.setStyleSheet("background: transparent; color: #212121;")

        layout.addWidget(top_row)
        layout.addWidget(self.value_label)
        layout.addWidget(self.flag_label, alignment=Qt.AlignRight)

        self.set_state(3.7, status="normal", is_min=False, is_max=False, balancing=False)

    def set_state(self, voltage: float, status: str, is_min: bool, is_max: bool, balancing: bool):
        colors = {
            "critical": ("#FFCDD2", "#C62828", "#E53935"),  # bg, text, border
            "warning": ("#FFE0B2", "#E65100", "#FB8C00"),
            "normal": ("#C8E6C9", "#1B5E20", "#43A047"),
        }
        bg, text_color, border_color = colors.get(status, colors["normal"])

        border_width = 2
        if is_max:
            border_color = "#1E88E5"  # bleu = Vmax
            border_width = 3
        elif is_min:
            border_color = "#8E24AA"  # violet = Vmin
            border_width = 3

        self.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border: {border_width}px solid {border_color}; "
            f"border-radius: 6px; }}"
        )
        self.value_label.setStyleSheet(f"background: transparent; color: {text_color};")
        self.value_label.setText(f"{voltage:.3f} V")

        flags = []
        if balancing:
            flags.append("⚡")
        if is_max:
            flags.append("MAX")
        if is_min:
            flags.append("MIN")
        self.flag_label.setText(" ".join(flags))

        tip = f"Cellule {self.index}: {voltage:.3f} V — {status.upper()}"
        if balancing:
            tip += " (équilibrage actif)"
        self.setToolTip(tip)


class CellVoltageGrid(QWidget):
    """
    Grille de N cellules. Calcule automatiquement min/max, statut par seuil,
    et l'écart max (delta) affiché en en-tête.

    Seuils par défaut calibrés pour LiPo 1S (3.0V - 4.2V nominal / 3.7V storage):
      critical: V < 3.0V ou V > 4.20V
      warning : V < 3.30V ou V > 4.15V
      normal  : sinon
    """

    def __init__(self, num_cells: int = 10, columns: int = 5, parent=None):
        super().__init__(parent)
        self.num_cells = num_cells
        self.columns = columns

        self.critical_low = 3.00
        self.warning_low = 3.30
        self.warning_high = 4.15
        self.critical_high = 4.20
        self.imbalance_warning_v = 0.05   # delta au-dessus duquel on signale un déséquilibre

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        header_row = QVBoxLayout()
        self.delta_label = QLabel("Δ tension: -- V")
        self.delta_label.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
        self.delta_label.setStyleSheet("color: #616161;")
        header_row.addWidget(self.delta_label)
        outer.addLayout(header_row)

        self.grid = QGridLayout()
        self.grid.setSpacing(6)
        outer.addLayout(self.grid)

        self.cards = []
        for i in range(1, num_cells + 1):
            card = CellCard(i)
            row = (i - 1) // columns
            col = (i - 1) % columns
            self.grid.addWidget(card, row, col)
            self.cards.append(card)

    def update_cells(self, voltages, balancing_indices=None):
        """
        voltages: liste de N tensions (float), ordre cellule 1..N
        balancing_indices: set/list d'indices (1-based) en équilibrage actif
        """
        if len(voltages) != self.num_cells:
            raise ValueError(f"Attendu {self.num_cells} tensions, reçu {len(voltages)}")

        balancing_indices = set(balancing_indices or [])
        v_min = min(voltages)
        v_max = max(voltages)
        delta = v_max - v_min

        delta_color = "#E53935" if delta > self.imbalance_warning_v else "#43A047"
        self.delta_label.setText(f"Δ tension: {delta:.3f} V   (min {v_min:.3f} V / max {v_max:.3f} V)")
        self.delta_label.setStyleSheet(f"color: {delta_color}; font-weight: 600;")

        for i, v in enumerate(voltages, start=1):
            if v <= self.critical_low or v >= self.critical_high:
                status = "critical"
            elif v <= self.warning_low or v >= self.warning_high:
                status = "warning"
            else:
                status = "normal"

            is_min = (v == v_min)
            is_max = (v == v_max)
            card = self.cards[i - 1]
            card.set_state(v, status, is_min, is_max, i in balancing_indices)


if __name__ == "__main__":
    import sys
    import random
    from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton

    app = QApplication(sys.argv)
    win = QMainWindow()
    win.setWindowTitle("Aperçu CellVoltageGrid — Pack 10S/36V")

    central = QWidget()
    layout = QVBoxLayout(central)
    grid_widget = CellVoltageGrid(num_cells=10, columns=5)
    layout.addWidget(grid_widget)

    def randomize():
        base = 3.7
        voltages = [round(base + random.uniform(-0.08, 0.08), 3) for _ in range(10)]
        # injecte une anomalie de temps en temps pour tester les couleurs
        if random.random() < 0.3:
            voltages[random.randint(0, 9)] = round(random.uniform(2.9, 3.05), 3)
        balancing = set(random.sample(range(1, 11), k=random.randint(0, 2)))
        grid_widget.update_cells(voltages, balancing)

    btn = QPushButton("Simuler nouvelles tensions")
    btn.clicked.connect(randomize)
    layout.addWidget(btn)

    randomize()
    win.setCentralWidget(central)
    win.resize(520, 260)
    win.show()
    sys.exit(app.exec())
