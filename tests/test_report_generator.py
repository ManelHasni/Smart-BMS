"""
test_report_generator.py -- Tests de non-regression pour la generation de PDF.

On ne verifie pas le rendu visuel (hors de portee de tests unitaires), seulement
que le pipeline ne plante pas pour chaque type de diagnostic et produit bien un
fichier PDF non vide.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from report_generator import generate_pdf_report


def make_snapshot(label="normal", fault_index=None):
    return {
        "label": label,
        "confidence": 0.87,
        "probabilities": {
            "normal": 0.87, "desequilibre_cellulaire": 0.08,
            "emballement_thermique": 0.02, "surtension_charge": 0.02,
            "resistance_anormale": 0.01,
        },
        "pack_v": 37.5,
        "current": 5.2,
        "temp": 26.0,
        "soc": 74.0,
        "soh": 98.5,
        "cell_voltages": [3.75] * 10,
        "fault_index": fault_index,
    }


class TestGeneratePdfReport:
    @pytest.mark.parametrize("label", [
        "normal", "desequilibre_cellulaire", "emballement_thermique",
        "surtension_charge", "resistance_anormale",
    ])
    def test_generates_non_empty_pdf_for_each_label(self, tmp_path, label):
        out_path = tmp_path / f"rapport_{label}.pdf"
        generate_pdf_report(str(out_path), make_snapshot(label=label))
        assert out_path.exists()
        assert out_path.stat().st_size > 0

    def test_pdf_starts_with_valid_header(self, tmp_path):
        """Verifie une signature de fichier PDF minimale (%PDF-)."""
        out_path = tmp_path / "rapport.pdf"
        generate_pdf_report(str(out_path), make_snapshot())
        with open(out_path, "rb") as f:
            header = f.read(5)
        assert header == b"%PDF-"

    def test_handles_fault_index_set(self, tmp_path):
        out_path = tmp_path / "rapport_fault.pdf"
        generate_pdf_report(str(out_path), make_snapshot(label="surtension_charge", fault_index=4))
        assert out_path.exists()
