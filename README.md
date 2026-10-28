
# Smart BMS — diagnostic prédictif de batteries pour véhicules électriques légers

>  Desktop application (Python / PySide6) that simulates a 10S lithium battery pack, detects faults with a Random Forest model, explains its diagnosis, estimates remaining useful life and supervises a small fleet of packs. Everything runs in simulation: no hardware required.

Application de bureau (Python / PySide6) qui **simule un pack de batteries 10S / 36 V**, **détecte les défauts par apprentissage automatique**, **explique son diagnostic**, **estime la durée de vie restante (RUL)** et **supervise une flotte de packs**. Projet réalisé lors d'un stage d'ingénieur sur la gestion de batteries de véhicules électriques légers (vélomobiles, e-bikes).

## Fonctionnalités

**Simulation physique**
- Circuit équivalent de Thévenin (courbe OCV, R0, R1/C1), comptage coulombmétrique, modèle thermique.
- Trois chimies : Li-ion/LiPo, LiFePO4, sodium-ion.
- Équilibrage passif des cellules et vieillissement du SOH (usage, température, scénarios de défaut).

**Diagnostic par apprentissage automatique**
- Random Forest à 5 classes : normal, déséquilibre cellulaire, emballement thermique, surtension de charge, résistance anormale.
- 12 variables extraites d'une fenêtre glissante de 30 mesures ; probabilité par classe.
- Explicabilité simplifiée : importance globale des variables × écart à la normale.
- Durée de vie restante (RUL) par régression linéaire du SOH vers le seuil de fin de vie (80 %).

**Protection et maintenance**
- Seuils configurables (surtension, sous-tension, surintensités, court-circuit, surchauffe, équilibrage) et compteurs d'événements.
- Interrupteurs Charge / Décharge / AutoBalance ; actions Reset BMS, Close BMS, Reset usine.
- Actions sensibles protégées par PIN (haché en SHA-256 ; **PIN par défaut `1401`, réservé à la démonstration**).

**Données et rapports**
- Historique du SOH sur plusieurs sessions (SQLite) avec durée de rétention configurable.
- Export CSV, PDF de diagnostic (1 page) et rapport de synthèse (3 pages).
- Enregistrement, rejeu et comparaison de scénarios ; journal d'événements.

**Supervision de flotte** — 5 packs simulés en parallèle avec statut Normal / Surveillance / Alarme.

**Interface** — 4 pages, thème clair/sombre à chaud, icônes vectorielles, légende, raccourcis clavier, écran de démarrage.


## Installation

Testé avec Python 3.14 (Windows) et 3.12 (Linux).

```bash
git clone https://github.com/<utilisateur>/<depot>.git
cd <depot>
python -m venv .venv
.venv\Scripts\activate          # Linux / macOS : source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Utilisation

| Raccourci | Action |
|---|---|
| `Ctrl+1` … `Ctrl+4` | Diagnostic, Configuration, Rapports, Flotte |
| `Ctrl+E` / `Ctrl+Shift+E` | Export PDF / CSV |
| `Ctrl+T` | Thème clair / sombre |

Le menu déroulant « Mode simulation » en haut de la page Diagnostic permet d'injecter un scénario de défaut.

## Tests

```bash
pip install -r requirements-test.txt
python -m pytest tests                                   # 74 tests
python -m pytest tests --cov=. --cov-config=.coveragerc --cov-report=html
```

Sur une machine sans écran : `QT_QPA_PLATFORM=offscreen`. Les tests utilisent des réglages et une base temporaires et ne touchent pas à vos données.

## Générer l'exécutable Windows

```bat
build_exe.bat
```

Produit `dist\SmartBMS\SmartBMS.exe` (PyInstaller).



Les dossiers `logs/`, `recordings/` et le fichier `history.db` sont créés à l'exécution et ignorés par Git.

## Contexte et auteur

Projet réalisé dans le cadre d'un stage d'ingénieur.

**Manel Hasni** — projet de fin d'études (PFA), mécatronique.

## Licence

Aucune licence pour l'instant : tous droits réservés tant qu'un fichier `LICENSE` n'est pas ajouté.