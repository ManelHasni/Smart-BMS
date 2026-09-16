"""
CircularGauge - Jauge circulaire type "compteur" pour SOC / SOH
Inspiré des apps BMS commerciales (Xiaoxiang BMS)

Usage:
    gauge = CircularGauge(label="SOC", unit="%")
    gauge.set_value(87.5)
    gauge.set_subtitle("Remaining: 8.75 AH")
"""

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QConicalGradient
from PySide6.QtCore import Qt, QRectF, Property, QPropertyAnimation, QEasingCurve, Signal


class CircularGauge(QWidget):
    """
    Jauge circulaire animée (270°, de -225° à +45°) avec:
    - couleur qui évolue rouge -> orange -> vert selon la valeur
    - grande valeur centrale + label
    - sous-titre optionnel (ex: "Remaining: 8.75 AH")
    - animation fluide lors des changements de valeur
    """

    valueChanged = Signal(float)

    # Seuils de couleur (modifiable selon SOC ou SOH)
    CRITICAL_THRESHOLD = 20
    WARNING_THRESHOLD = 50

    def __init__(self, label="SOC", unit="%", min_value=0, max_value=100, parent=None,
                 track_color="#E0E0E0", value_text_color="#212121", label_text_color="#757575",
                 subtitle_text_color="#9E9E9E", normal_color="#43A047", warning_color="#FB8C00",
                 critical_color="#E53935"):
        super().__init__(parent)
        self._label = label
        self._unit = unit
        self._min_value = min_value
        self._max_value = max_value
        self._value = 0.0
        self._display_value = 0.0
        self._subtitle = ""

        # Theming (permet d'adapter la jauge a une palette sombre comme celle du dashboard)
        self._track_color = QColor(track_color)
        self._value_text_color = QColor(value_text_color)
        self._label_text_color = QColor(label_text_color)
        self._subtitle_text_color = QColor(subtitle_text_color)
        self._normal_color = QColor(normal_color)
        self._warning_color = QColor(warning_color)
        self._critical_color = QColor(critical_color)

        self.setMinimumSize(90, 90)
        self.setMaximumSize(120, 120)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        self._anim = QPropertyAnimation(self, b"displayValue")
        self._anim.setDuration(450)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    # ---- Qt Property pour permettre l'animation ----
    def getDisplayValue(self):
        return self._display_value

    def setDisplayValue(self, v):
        self._display_value = v
        self.update()

    displayValue = Property(float, getDisplayValue, setDisplayValue)

    # ---- API publique ----
    def set_value(self, value: float, animate: bool = True):
        value = max(self._min_value, min(self._max_value, value))
        self._value = value
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._display_value)
            self._anim.setEndValue(value)
            self._anim.start()
        else:
            self.setDisplayValue(value)
        self.valueChanged.emit(value)

    def value(self) -> float:
        return self._value

    def set_subtitle(self, text: str):
        self._subtitle = text
        self.update()

    def set_thresholds(self, critical: float, warning: float):
        """Personnalise les seuils de couleur (ex: SOH plus tolérant que SOC)."""
        self.CRITICAL_THRESHOLD = critical
        self.WARNING_THRESHOLD = warning
        self.update()

    def _color_for_value(self, v: float) -> QColor:
        if v <= self.CRITICAL_THRESHOLD:
            return self._critical_color
        elif v <= self.WARNING_THRESHOLD:
            return self._warning_color
        else:
            return self._normal_color

    # ---- Rendu ----
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        side = min(self.width(), self.height())
        rect = QRectF(
            (self.width() - side) / 2 + side * 0.08,
            (self.height() - side) / 2 + side * 0.08,
            side * 0.84,
            side * 0.84,
        )

        start_angle = 225 * 16   # Qt angles en 1/16 de degré, sens anti-horaire depuis 3h
        span_total = -270 * 16   # arc de 270° dans le sens horaire

        # Piste de fond
        track_pen = QPen(self._track_color, side * 0.07, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, start_angle, span_total)

        # Arc de valeur
        ratio = 0.0
        if self._max_value > self._min_value:
            ratio = (self._display_value - self._min_value) / (self._max_value - self._min_value)
        ratio = max(0.0, min(1.0, ratio))

        color = self._color_for_value(self._display_value)
        value_pen = QPen(color, side * 0.07, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(value_pen)
        painter.drawArc(rect, start_angle, int(span_total * ratio))

        # Texte central : valeur
        painter.setPen(self._value_text_color)
        value_font = QFont("Consolas", int(side * 0.16), QFont.Bold)
        painter.setFont(value_font)
        value_text = f"{self._display_value:.0f}{self._unit}"
        text_rect = QRectF(rect.x() - side * 0.08, rect.y() + side * 0.28, side * 1.0, side * 0.3)
        painter.drawText(text_rect, Qt.AlignCenter, value_text)

        # Label (ex: "SOC")
        label_font = QFont("Consolas", int(side * 0.075), QFont.DemiBold)
        painter.setFont(label_font)
        painter.setPen(self._label_text_color)
        label_rect = QRectF(rect.x() - side * 0.08, rect.y() + side * 0.52, side * 1.0, side * 0.14)
        painter.drawText(label_rect, Qt.AlignCenter, self._label)

        # Sous-titre (ex: "Remaining: 8.75 AH")
        if self._subtitle:
            sub_font = QFont("Consolas", int(side * 0.05))
            painter.setFont(sub_font)
            painter.setPen(self._subtitle_text_color)
            sub_rect = QRectF(rect.x() - side * 0.1, rect.y() + side * 0.68, side * 1.2, side * 0.12)
            painter.drawText(sub_rect, Qt.AlignCenter, self._subtitle)


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout

    app = QApplication(sys.argv)
    win = QMainWindow()
    win.setWindowTitle("Aperçu CircularGauge")
    central = QWidget()
    layout = QHBoxLayout(central)

    soc_gauge = CircularGauge(label="SOC", unit="%")
    soc_gauge.set_value(87)
    soc_gauge.set_subtitle("Remaining: 8.75 AH")

    soh_gauge = CircularGauge(label="SOH", unit="%")
    soh_gauge.set_thresholds(critical=70, warning=85)
    soh_gauge.set_value(94)
    soh_gauge.set_subtitle("Cycles: 142")

    layout.addWidget(soc_gauge)
    layout.addWidget(soh_gauge)

    win.setCentralWidget(central)
    win.resize(500, 260)
    win.show()
    sys.exit(app.exec())
