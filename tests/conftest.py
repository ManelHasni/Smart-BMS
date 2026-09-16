"""
conftest.py -- fixtures partagees pour la suite de tests Smart BMS.

Principes :
- Un seul QApplication par processus de test (fixture session-scoped).
- Chaque test qui a besoin d'une MainWindow complete recoit une instance ISOLEE
  (QSettings et history.db pointes vers un dossier temporaire), pour ne jamais
  toucher a la vraie configuration/l'historique de l'utilisateur sur sa machine.
"""

import os
import sys
from pathlib import Path

# Doit etre defini AVANT tout import de PySide6 (evite d'exiger un vrai serveur
# d'affichage pour lancer les tests, y compris en CI sans ecran).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture()
def isolated_window(qapp, tmp_path, monkeypatch):
    """Cree une MainWindow avec QSettings et history.db isoles dans un dossier
    temporaire propre a chaque test -- aucun etat partage entre tests, et la
    vraie configuration de l'utilisateur n'est jamais touchee.

    Limite connue : le fichier de LOG texte (logging.basicConfig) est configure
    une seule fois, au tout premier import de main.py, avant que ce fixture ne
    puisse le rediriger -- les tests ecrivent donc quelques lignes de log dans
    le vrai dossier logs/ du projet. Sans consequence (juste informatif), mais
    documente ici pour eviter toute confusion en relisant ce fichier plus tard.
    """
    import main as main_module
    from PySide6.QtCore import QSettings
    QSettings.setDefaultFormat(QSettings.IniFormat)

    ini_path = tmp_path / "settings.ini"

    def _fake_settings(*args, **kwargs):
        return QSettings(str(ini_path), QSettings.IniFormat)

    monkeypatch.setattr(main_module, "QSettings", _fake_settings)
    monkeypatch.setattr(main_module, "WRITABLE_DIR", tmp_path)

    win = main_module.MainWindow()
    yield win
    win.close()
