"""
recording_store.py -- Enregistrement/rejeu/comparaison de scenarios pour le Smart BMS.

Un "enregistrement" est simplement la liste des lignes deja produites par la session
courante (le meme format que celui utilise pour l'export CSV : timestamp, tick,
pack_v, current, temp, soc, soh, scenario, cell_1_v..cell_10_v), sauvegardee en JSON
sous un nom choisi par l'utilisateur. Permet de :
  - reprendre une sequence precise plus tard pour l'observer a nouveau (rejeu)
  - comparer visuellement deux sequences (ex: seuils differents sur le meme scenario)
"""

import json
from pathlib import Path


class RecordingStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(exist_ok=True)

    def save(self, name: str, rows: list) -> Path:
        safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).strip()
        safe_name = safe_name.replace(" ", "_") or "scenario"
        path = self.directory / f"{safe_name}.json"
        # Evite d'ecraser silencieusement un enregistrement existant du meme nom
        counter = 1
        while path.exists():
            path = self.directory / f"{safe_name}_{counter}.json"
            counter += 1
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"name": name, "rows": rows}, f)
        return path

    def list_recordings(self):
        """Renvoie [(label_affiche, path)] trie par date de modification (recent d'abord)."""
        files = sorted(self.directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        results = []
        for path in files:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                n_points = len(data.get("rows", []))
                results.append((f"{data.get('name', path.stem)}  ({n_points} points)", path))
            except (json.JSONDecodeError, OSError):
                continue
        return results

    def load(self, path: Path) -> list:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("rows", [])

    def delete(self, path: Path):
        Path(path).unlink(missing_ok=True)
