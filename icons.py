"""
icons.py -- Set d'icones vectorielles coherentes pour Smart BMS.

Remplace les emojis Unicode (rendu incoherent selon l'OS/la police) par de vraies
icones SVG dessinees dans un style unique : traits fins (stroke), coins arrondis,
viewBox 24x24 -- meme esprit que Feather/Tabler Icons, dessinees a la main ici pour
ne dependre d'aucun fichier externe ni police d'icones a installer.

Usage:
    from icons import icon_pixmap, IconLabel, set_button_icon

    label = QLabel(); label.setPixmap(icon_pixmap("zap", "#59F2A0", 14))

    row = IconLabel("battery", "BANC DE CELLULES", color="#8FA79B")

    set_button_icon(my_button, "check-circle", "#59F2A0")
"""

from PySide6.QtCore import Qt, QByteArray, QSize
from PySide6.QtGui import QPixmap, QPainter, QIcon
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel

_SVG_WRAPPER = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>"""

# Chaque icone : liste de balises SVG (path/circle/line/rect/polyline) formant un dessin
# au trait, coherent avec les autres (memes proportions, meme epaisseur de trait).
ICONS = {
    "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" fill="{color}" stroke="none"/>',
    "plug": '<path d="M9 2v6M15 2v6M7 8h10v4a5 5 0 0 1-5 5 5 5 0 0 1-5-5V8z"/><path d="M12 17v5"/>',
    "thermometer": '<path d="M12 3a2 2 0 0 0-2 2v9.5a4 4 0 1 0 4 0V5a2 2 0 0 0-2-2z"/><circle cx="12" cy="18" r="1.3" fill="{color}" stroke="none"/>',
    "scale": '<path d="M12 3v18M5 8l-3 6a3.5 3.5 0 0 0 6 0zM19 8l-3 6a3.5 3.5 0 0 0 6 0zM5 8h14M9 21h6"/>',
    "lock": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "battery": '<rect x="7" y="4" width="10" height="17" rx="2"/><path d="M10 1h4v3h-4z" fill="{color}" stroke="none"/>',
    "radio": '<circle cx="12" cy="14" r="2.2"/><path d="M7.5 9.5a6.5 6.5 0 0 1 9 0M4.5 6.5a11 11 0 0 1 15 0M9.8 12.5a2.8 2.8 0 0 1 4.4 0"/>',
    "activity": '<polyline points="2 14 7 14 9.5 6 14.5 20 17 14 22 14"/>',
    "sliders": '<line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="18" x2="20" y2="18"/><circle cx="9" cy="6" r="2" fill="{bg}" /><circle cx="16" cy="12" r="2" fill="{bg}"/><circle cx="7" cy="18" r="2" fill="{bg}"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><polyline points="8 12.5 11 15.5 16 9"/>',
    "flame": '<path d="M12 2c1 3.5-3 4.5-3 8.5a3 3 0 0 0 6 0c0-1.2-.6-2-1-2.7 2 1 3 3 3 5.2a5 5 0 0 1-10 0C7 8.5 11 7 12 2z"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M19.4 13.5a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.9 2.9l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.9-2.9l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.6-1h-.2a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.9-2.9l.1.1a1.7 1.7 0 0 0 1.9.3h.1a1.7 1.7 0 0 0 1-1.6v-.2a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.6h.1a1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.9 2.9l-.1.1a1.7 1.7 0 0 0-.3 1.9v.1a1.7 1.7 0 0 0 1.6 1h.2a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.6 1z"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15.5 14"/>',
    "tool": '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.8 2.8-2-2z"/>',
    "file-text": '<path d="M14 2H7a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/>',
    "folder-down": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9.5 13 12 15.5 14.5 13"/><line x1="12" y1="10" x2="12" y2="15.5"/>',
    "list": '<line x1="9" y1="6" x2="20" y2="6"/><line x1="9" y1="12" x2="20" y2="12"/><line x1="9" y1="18" x2="20" y2="18"/><circle cx="4.5" cy="6" r="1.1" fill="{color}" stroke="none"/><circle cx="4.5" cy="12" r="1.1" fill="{color}" stroke="none"/><circle cx="4.5" cy="18" r="1.1" fill="{color}" stroke="none"/>',
    "bar-chart": '<line x1="5" y1="21" x2="5" y2="12"/><line x1="12" y1="21" x2="12" y2="7"/><line x1="19" y1="21" x2="19" y2="15"/><line x1="3" y1="21" x2="21" y2="21"/>',
    "info": '<circle cx="12" cy="12" r="9.3"/><line x1="12" y1="11" x2="12" y2="16.5"/><circle cx="12" cy="7.6" r="1.05" fill="{color}" stroke="none"/>',
    "bell": '<path d="M6 9a6 6 0 0 1 12 0c0 4.5 1.5 6 1.5 6h-15S6 13.5 6 9z"/><path d="M10 19a2 2 0 0 0 4 0"/>',
    "refresh-cw": '<polyline points="17 2 21 6 17 10"/><path d="M3 12a9 9 0 0 1 15.5-6.2L21 6"/><polyline points="7 22 3 18 7 14"/><path d="M21 12a9 9 0 0 1-15.5 6.2L3 18"/>',
    "power": '<line x1="12" y1="2" x2="12" y2="12"/><path d="M6.3 6.3a9 9 0 1 0 11.4 0"/>',
    "alert-triangle": '<path d="M10.3 3.8 2.6 18a1.7 1.7 0 0 0 1.5 2.5h15.8a1.7 1.7 0 0 0 1.5-2.5L13.7 3.8a1.7 1.7 0 0 0-3.4 0z"/><line x1="12" y1="9.5" x2="12" y2="14"/><circle cx="12" cy="17.2" r="0.9" fill="{color}" stroke="none"/>',
    "cpu": '<rect x="6" y="6" width="12" height="12" rx="1.5"/><rect x="9.5" y="9.5" width="5" height="5"/><line x1="12" y1="1.5" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22.5"/><line x1="1.5" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22.5" y2="12"/>',
    "shield": '<path d="M12 2 4 5v6c0 5 3.4 8.7 8 11 4.6-2.3 8-6 8-11V5z"/>',
    "download": '<path d="M12 3v12"/><polyline points="7 10.5 12 15.5 17 10.5"/><path d="M4 18.5h16v2H4z" fill="{color}" stroke="none"/>',
    "chevron-left": '<polyline points="15 5 8 12 15 19"/>',
    "chevron-right": '<polyline points="9 5 16 12 9 19"/>',
    "trending-down": '<polyline points="3 7 10 14 14 10 21 17"/><polyline points="21 10 21 17 14 17"/>',
    "grid": '<rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="8" rx="1.5"/><rect x="3" y="13" width="8" height="8" rx="1.5"/><rect x="13" y="13" width="8" height="8" rx="1.5"/>',
    "play": '<polygon points="6 3 20 12 6 21" fill="{color}" stroke="none"/>',
    "pause": '<rect x="6" y="4" width="4" height="16" rx="1" fill="{color}" stroke="none"/><rect x="14" y="4" width="4" height="16" rx="1" fill="{color}" stroke="none"/>',
    "layers": '<polygon points="12 2 22 8 12 14 2 8"/><polyline points="2 15 12 21 22 15"/><polyline points="2 11.5 12 17.5 22 11.5"/>',
    "save": '<path d="M5 3h11l3 3v15H5z"/><rect x="8" y="3" width="8" height="6"/><rect x="7" y="14" width="10" height="7"/>',
    "help-circle": '<circle cx="12" cy="12" r="9.3"/><path d="M9.2 9.2a2.8 2.8 0 1 1 4.6 2.1c-.9.7-1.6 1.3-1.6 2.4"/><circle cx="12" cy="17.2" r="0.9" fill="{color}" stroke="none"/>',
}


def _svg_source(name: str, color: str = "#E8F5EE", bg: str = "#0B0F0D", stroke: float = 1.8) -> str:
    body = ICONS[name].format(color=color, bg=bg)
    return _SVG_WRAPPER.format(color=color, stroke=stroke, body=body)


def icon_pixmap(name: str, color: str = "#E8F5EE", size: int = 16, bg: str = "#0B0F0D",
                stroke: float = 1.8) -> QPixmap:
    """Rend une icone vectorielle en QPixmap a la taille et couleur demandees."""
    svg = _svg_source(name, color=color, bg=bg, stroke=stroke)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    return pix


def icon_qicon(name: str, color: str = "#E8F5EE", size: int = 16, bg: str = "#0B0F0D") -> QIcon:
    return QIcon(icon_pixmap(name, color=color, size=size, bg=bg))


def set_button_icon(button, name: str, color: str = "#E8F5EE", size: int = 14, bg: str = "#0B0F0D"):
    """Attache une icone vectorielle a un QPushButton existant (a gauche du texte)."""
    button.setIcon(icon_qicon(name, color=color, size=size, bg=bg))
    button.setIconSize(QSize(size, size))


class IconLabel(QWidget):
    """Widget composite icone + texte, pour remplacer les QLabel 'emoji + titre'.
    S'utilise comme un QLabel classique dans un layout."""

    def __init__(self, icon_name: str, text: str, color: str = "#E8F5EE",
                 icon_color: str = None, size: int = 13, bold: bool = False,
                 letter_spacing: bool = False, font_family: str = None, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(icon_pixmap(icon_name, icon_color or color, size))
        icon_lbl.setStyleSheet("background:transparent; border:none;")
        layout.addWidget(icon_lbl)

        text_lbl = QLabel(text)
        weight = "font-weight:bold;" if bold else ""
        spacing = "letter-spacing:1px;" if letter_spacing else ""
        family = f"font-family:{font_family};" if font_family else ""
        text_lbl.setStyleSheet(f"color:{color}; font-size:{size-2}px; {weight} {spacing} {family} background:transparent; border:none;")
        layout.addWidget(text_lbl)
        layout.addStretch()
        self.text_label = text_lbl
        self.icon_label = icon_lbl

    def setText(self, text):
        self.text_label.setText(text)

    def setStyleSheet(self, qss):
        self.text_label.setStyleSheet(self.text_label.styleSheet() + qss)
