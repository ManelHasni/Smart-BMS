# Smart BMS — Dashboard desktop PySide6

Application desktop native, simulation autonome + vrai modele Random Forest charge en memoire
(pas de backend, pas de navigateur, pas de matériel requis).

## Installation

```bash
pip install -r requirements.txt
```

## Lancer

```bash
python main.py
```

Une fenetre s'ouvre avec le dashboard temps reel. Clique sur les boutons "Injecter un scenario"
pour declencher un defaut (desequilibre, emballement thermique, surtension, resistance anormale) et
observer le modele Random Forest le detecter en direct (~10-60 secondes selon le defaut, le temps
que la fenetre de mesures glissante accumule assez de signal — c'est le meme comportement que le
notebook : un defaut n'est jamais instantanement evident, il faut qu'il se manifeste dans les
mesures).

## Fichiers

- `main.py` — interface graphique (PySide6 + pyqtgraph)
- `battery_model.py` — modele physique du pack (circuit de Thevenin), identique au notebook
- `battery_rf_model.pkl` / `battery_scaler.pkl` — le vrai modele entraine, charge directement en
  memoire via `joblib.load()` (pas d'appel HTTP)

## Notes

- Le diagnostic est recalcule a chaque tick une fois que 10 lectures sont disponibles dans la
  fenetre glissante (30 lectures max, comme a l'entrainement).
- Si tu veux brancher un vrai capteur plus tard, remplace `LiveSimulator.step()` dans
  `battery_model.py` par une lecture serie (`pyserial`) depuis l'Arduino/NodeMCU — le reste du
  dashboard n'a pas besoin de changer.
