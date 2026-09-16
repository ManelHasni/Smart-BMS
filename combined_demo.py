import sys, random
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtGui import QFont
from gauge_widget import CircularGauge
from cell_grid_widget import CellVoltageGrid

app = QApplication(sys.argv)
win = QMainWindow()
win.setWindowTitle("Smart BMS - Pack 10S/36V - Aperçu")
win.setStyleSheet("background-color: #FAFAFA;")

central = QWidget()
outer = QVBoxLayout(central)

title = QLabel("Smart BMS — Surveillance Pack 10S / 36V")
title.setFont(QFont("Segoe UI", 13, QFont.Bold))
title.setStyleSheet("color: #212121; padding: 6px;")
outer.addWidget(title)

top_row = QHBoxLayout()
soc = CircularGauge(label="SOC", unit="%")
soc.set_value(78, animate=False)
soc.set_subtitle("Remaining: 7.80 AH")

soh = CircularGauge(label="SOH", unit="%")
soh.set_thresholds(critical=70, warning=85)
soh.set_value(93, animate=False)
soh.set_subtitle("Cycles: 142")

top_row.addWidget(soc)
top_row.addWidget(soh)
outer.addLayout(top_row)

grid = CellVoltageGrid(num_cells=10, columns=5)
grid.update_cells([3.70,3.65,3.72,3.68,2.95,3.71,3.69,4.18,3.70,3.66], balancing_indices={2,8})
outer.addWidget(grid)

win.setCentralWidget(central)
win.resize(560, 480)
win.show()

win.grab().save("/home/claude/preview.png")
print("saved")
