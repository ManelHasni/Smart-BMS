#!/usr/bin/env python3
"""Applique le theme sombre/clair (commutable a chaud) a main.py et icons.py.
Usage : python apply_theme_patch.py [dossier_du_projet]   (defaut : dossier du script)
Idempotent : ne fait rien si deja applique. Echoue proprement si un motif est introuvable."""
import re
import sys
from pathlib import Path

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
main_p, icons_p = root / "main.py", root / "icons.py"
s = main_p.read_text(encoding="utf-8")
ic = icons_p.read_text(encoding="utf-8")

if "def apply_theme(" in s:
    print("Theme deja applique, rien a faire.")
    sys.exit(0)


def rep(text, old, new, label, count=1):
    n = text.count(old)
    if n != count:
        sys.exit(f"[ECHEC] {label}: {n} occurrence(s) trouvee(s), {count} attendue(s)")
    return text.replace(old, new)


# A) Palette -> THEMES + apply_theme
s = rep(s, '''# --- Palette ---
BG = "#0B0F0D"
SURFACE = "#131A17"
BORDER = "#1C2620"
TEXT = "#E8F5EE"
MUTED = "#7C9686"
DIM = "#4E625A"
GREEN = "#59F2A0"
COPPER = "#D98E4A"
''', '''# --- Palette (theme sombre/clair, commutable a chaud sans redemarrage) ---
THEMES = {
    "dark": {
        "BG": "#0B0F0D", "SURFACE": "#131A17", "BORDER": "#1C2620",
        "TEXT": "#E8F5EE", "MUTED": "#7C9686", "DIM": "#4E625A",
        "GREEN": "#59F2A0", "COPPER": "#D98E4A",
    },
    "light": {
        "BG": "#F5F7F6", "SURFACE": "#FFFFFF", "BORDER": "#DCE3DF",
        "TEXT": "#152018", "MUTED": "#5B6B63", "DIM": "#8B9A93",
        "GREEN": "#1E9E5A", "COPPER": "#B5651D",
    },
}
BG = SURFACE = BORDER = TEXT = MUTED = DIM = GREEN = COPPER = None


def apply_theme(name: str):
    """Bascule la palette globale. A appeler AVANT (re)construction de l'UI : toutes
    les f-strings de style lisent ces constantes au moment ou les widgets sont crees,
    donc un rebuild complet de l'UI suffit a appliquer le nouveau theme partout."""
    global BG, SURFACE, BORDER, TEXT, MUTED, DIM, GREEN, COPPER
    p = THEMES.get(name, THEMES["dark"])
    BG, SURFACE, BORDER = p["BG"], p["SURFACE"], p["BORDER"]
    TEXT, MUTED, DIM = p["TEXT"], p["MUTED"], p["DIM"]
    GREEN, COPPER = p["GREEN"], p["COPPER"]


apply_theme("dark")
''', "palette")

# B) Chargement du theme sauvegarde (le style de fenetre doit etre reapplique APRES apply_theme)
s = rep(s, '''        self.settings = QSettings("Akkurad", "SmartBMS")
''', '''        self.settings = QSettings("Akkurad", "SmartBMS")

        self.current_theme = self.settings.value("appearance/theme", "dark")
        if self.current_theme not in THEMES:
            self.current_theme = "dark"
        apply_theme(self.current_theme)
        self.setStyleSheet(f"background:{BG}; color:{TEXT};")
        self._current_nav_key = "diagnostic"
''', "chargement theme")

# C) Bouton theme dans l'en-tete
s = rep(s, '''        about_btn.clicked.connect(lambda: AboutDialog(self).exec())
        header.addWidget(about_btn, alignment=Qt.AlignVCenter)
''', '''        about_btn.clicked.connect(lambda: AboutDialog(self).exec())
        header.addWidget(about_btn, alignment=Qt.AlignVCenter)

        self.theme_btn = QPushButton()
        set_button_icon(self.theme_btn, "sun" if self.current_theme == "dark" else "moon", MUTED, size=15, bg=SURFACE)
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setFixedSize(30, 30)
        self.theme_btn.setStyleSheet(f"""
            QPushButton {{
                background:{SURFACE}; border:1px solid {BORDER};
                border-radius:15px; margin-left:6px;
            }}
            QPushButton:hover {{ border-color:{COPPER}; }}
        """)
        self.theme_btn.setToolTip("Changer de theme (Ctrl+T)")
        self.theme_btn.clicked.connect(self._toggle_theme)
        header.addWidget(self.theme_btn, alignment=Qt.AlignVCenter)
''', "bouton theme")

# D) Raccourcis : sortis de _build_ui (sinon dupliques a chaque rebuild)
s = rep(s, '''        # -- Raccourcis clavier (detail pro apprecie en demo live) --
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self._export_pdf)
        QShortcut(QKeySequence("Ctrl+Shift+E"), self, activated=self._export_csv)
        QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda: self._navigate_to("diagnostic"))
        QShortcut(QKeySequence("Ctrl+2"), self, activated=lambda: self._navigate_to("configuration"))
        QShortcut(QKeySequence("Ctrl+3"), self, activated=lambda: self._navigate_to("reports"))
        QShortcut(QKeySequence("Ctrl+4"), self, activated=lambda: self._navigate_to("fleet"))
''', '''        # Restaure la page active si on reconstruit l'UI (ex: changement de theme)
        if hasattr(self, "_current_nav_key"):
            self._navigate_to(self._current_nav_key)
''', "raccourcis (retrait)")

# E) Raccourcis crees une seule fois dans __init__ (+ Ctrl+T)
s = rep(s, '''        self._build_ui()

        self.timer = QTimer()''', '''        self._build_ui()

        # Raccourcis clavier : crees UNE SEULE FOIS ici (pas dans _build_ui).
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self._export_pdf)
        QShortcut(QKeySequence("Ctrl+Shift+E"), self, activated=self._export_csv)
        QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda: self._navigate_to("diagnostic"))
        QShortcut(QKeySequence("Ctrl+2"), self, activated=lambda: self._navigate_to("configuration"))
        QShortcut(QKeySequence("Ctrl+3"), self, activated=lambda: self._navigate_to("reports"))
        QShortcut(QKeySequence("Ctrl+4"), self, activated=lambda: self._navigate_to("fleet"))
        QShortcut(QKeySequence("Ctrl+T"), self, activated=self._toggle_theme)

        self.timer = QTimer()''', "raccourcis (init)")

# F) Memorisation de la page active
s = rep(s, '''        idx = self._nav_order.index(key)
        self.stack.setCurrentIndex(idx)''', '''        idx = self._nav_order.index(key)
        self._current_nav_key = key
        self.stack.setCurrentIndex(idx)''', "nav key")

# G) _toggle_theme + resynchronisation de l'etat affiche
s = rep(s, '''    def _nav_button_style(self, active):''', '''    def _toggle_theme(self):
        """Bascule sombre <-> clair a chaud : change la palette, sauvegarde le choix puis
        reconstruit l'interface (setCentralWidget libere l'ancienne). L'etat metier
        (simulateur, historiques, compteurs, timer) n'est pas touche."""
        self.current_theme = "light" if self.current_theme == "dark" else "dark"
        self.settings.setValue("appearance/theme", self.current_theme)
        apply_theme(self.current_theme)
        self.setStyleSheet(f"background:{BG}; color:{TEXT};")
        self._build_ui()
        self._resync_ui_after_rebuild()
        self._log(f"Theme -> {'clair' if self.current_theme == 'light' else 'sombre'}")

    def _resync_ui_after_rebuild(self):
        """Les widgets reconstruits repartent a zero : on reaffiche l'etat courant."""
        for key, count in self.protection_events.items():
            if key in self.event_labels:
                self.event_labels[key].setText(str(count))
        self._update_alarm_badge()
        self._set_scenario(self.sim.scenario)

    def _nav_button_style(self, active):''', "toggle theme")

# H) Valeur par defaut figee a l'import
s = rep(s, '''    def set_value(self, value, color=TEXT):
''', '''    def set_value(self, value, color=None):
        color = color or TEXT
''', "set_value")

# I) Icone sans bg explicite
s = rep(s, 'icon_pixmap("sliders", MUTED, 13))', 'icon_pixmap("sliders", MUTED, 13, bg=SURFACE))', "icone sliders")

# K) FleetCard : statuts resolus a l'appel (et non a l'import)
s = rep(s, '''    STATUS_STYLE = {
        "normal": (GREEN, "Normal"),
        "surveillance": ("#F5B942", "Surveillance"),
        "alarme": ("#FF5C4D", "Alarme"),
    }
''', '''    @staticmethod
    def _status_style():
        return {
            "normal": (GREEN, "Normal"),
            "surveillance": ("#F5B942", "Surveillance"),
            "alarme": ("#FF5C4D", "Alarme"),
        }
''', "FleetCard styles")
s = rep(s, 'self.STATUS_STYLE.get(data["status"], (MUTED, "?"))', 'self._status_style().get(data["status"], (MUTED, "?"))', "FleetCard appel")

# L) LegendDialog : couleurs resolues a l'ouverture (noms -> valeurs courantes)
m = re.search(r"    ENTRIES = \[\n.*?\n    \]\n", s, re.S)
if not m:
    sys.exit("[ECHEC] LegendDialog.ENTRIES introuvable")
blk = m.group(0)
new_blk = (blk.replace('", GREEN, "', '", "GREEN", "')
              .replace('", COPPER, "', '", "COPPER", "')
              .replace('", MUTED, "', '", "MUTED", "'))
s = s.replace(blk, new_blk)
s = rep(s, '''        for icon_name, color, text in self.ENTRIES:
''', '''        for icon_name, color, text in self.ENTRIES:
            color = globals().get(color, color)
''', "Legend boucle")

# J) icons.py : soleil / lune
ic = rep(ic, '''\n}\n\n\ndef _svg_source''', '''
    "sun": '<circle cx="12" cy="12" r="4.2"/><line x1="12" y1="2" x2="12" y2="4.5"/><line x1="12" y1="19.5" x2="12" y2="22"/><line x1="2" y1="12" x2="4.5" y2="12"/><line x1="19.5" y1="12" x2="22" y2="12"/><line x1="4.9" y1="4.9" x2="6.6" y2="6.6"/><line x1="17.4" y1="17.4" x2="19.1" y2="19.1"/><line x1="4.9" y1="19.1" x2="6.6" y2="17.4"/><line x1="17.4" y1="6.6" x2="19.1" y2="4.9"/>',
    "moon": '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.8 6.8 0 0 0 10.5 10.5z" fill="{color}" stroke="none"/>',
}


def _svg_source''', "icons sun/moon")

main_p.write_text(s, encoding="utf-8")
icons_p.write_text(ic, encoding="utf-8")
print("Theme applique : main.py et icons.py mis a jour.")
