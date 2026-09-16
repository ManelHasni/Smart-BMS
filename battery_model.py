"""
Modele physique de la batterie (pack LiPo 10S / 36V) — reutilise les memes equations
que le notebook d'entrainement, pour une simulation live cellule par cellule.
"""

import random

NUM_CELLS = 10
CAPACITY_NOMINAL_AH = 10.0
R0_NOMINAL = 0.012

# --- Profils de chimie (valeurs approximatives a but pedagogique, pas des datasheets
# constructeur : suffisant pour illustrer la difference de plage de tension et de
# forme de courbe OCV entre chimies, comme le permettent les vrais BMS commerciaux
# ANT BMS / JBD (bouton LiFePO4 / Li-ion / Sodium-ion). ---
CHEMISTRIES = {
    "liion": {
        "label": "Li-ion / LiPo",
        "v_min": 3.0, "v_max": 4.2, "v_nominal": 3.7,
        "soc_pts": [0.00, 0.05, 0.10, 0.20, 0.40, 0.60, 0.80, 0.90, 0.95, 1.00],
        "ocv_pts": [2.90, 3.25, 3.45, 3.58, 3.70, 3.80, 3.94, 4.06, 4.14, 4.20],
        "default_overvoltage": 4.20, "default_overvoltage_release": 4.15,
        "default_undervoltage": 3.00, "default_undervoltage_release": 3.10,
    },
    "lifepo4": {
        "label": "LiFePO4",
        "v_min": 2.50, "v_max": 3.65, "v_nominal": 3.2,
        # Plateau tres plat caracteristique du LiFePO4 (SOC 10%-90% quasi constant)
        "soc_pts": [0.00, 0.05, 0.10, 0.20, 0.40, 0.60, 0.80, 0.90, 0.95, 1.00],
        "ocv_pts": [2.50, 3.05, 3.20, 3.25, 3.28, 3.30, 3.32, 3.35, 3.45, 3.65],
        "default_overvoltage": 3.65, "default_overvoltage_release": 3.60,
        "default_undervoltage": 2.50, "default_undervoltage_release": 2.70,
    },
    "sodium": {
        "label": "Sodium-ion",
        "v_min": 2.00, "v_max": 3.80, "v_nominal": 3.0,
        "soc_pts": [0.00, 0.05, 0.10, 0.20, 0.40, 0.60, 0.80, 0.90, 0.95, 1.00],
        "ocv_pts": [2.00, 2.55, 2.75, 2.85, 2.95, 3.05, 3.20, 3.35, 3.55, 3.80],
        "default_overvoltage": 3.80, "default_overvoltage_release": 3.75,
        "default_undervoltage": 2.00, "default_undervoltage_release": 2.20,
    },
}

# Valeurs par defaut (retro-compatibilite : Li-ion, chimie actuelle du pack Akkurad)
V_MIN = CHEMISTRIES["liion"]["v_min"]
V_MAX = CHEMISTRIES["liion"]["v_max"]
SOC_PTS = CHEMISTRIES["liion"]["soc_pts"]
OCV_PTS = CHEMISTRIES["liion"]["ocv_pts"]

FAULT_CELL_IMBALANCE = 3
FAULT_CELL_RESISTANCE = 7
FAULT_CELL_OVERVOLT = 5


def ocv(soc: float, soc_pts=None, ocv_pts=None) -> float:
    soc_pts = soc_pts or SOC_PTS
    ocv_pts = ocv_pts or OCV_PTS
    soc = max(0.0, min(1.0, soc))
    for i in range(len(soc_pts) - 1):
        if soc_pts[i] <= soc <= soc_pts[i + 1]:
            span = soc_pts[i + 1] - soc_pts[i]
            frac = (soc - soc_pts[i]) / span if span > 0 else 0
            return ocv_pts[i] + frac * (ocv_pts[i + 1] - ocv_pts[i])
    return ocv_pts[-1]


class Cell:
    def __init__(self, capacity_ah, r0, r1=0.008, c1=2000.0, soc=0.9, soc_pts=None, ocv_pts=None):
        self.capacity_ah = capacity_ah
        self.r0 = r0
        self.r1 = r1
        self.c1 = c1
        self.soc = soc
        self.v1 = 0.0
        self.soc_pts = soc_pts or SOC_PTS
        self.ocv_pts = ocv_pts or OCV_PTS

    def step(self, current_a: float, dt_s: float = 1.0) -> float:
        self.soc -= (current_a * dt_s) / (self.capacity_ah * 3600.0)
        self.soc = max(0.0, min(1.0, self.soc))
        tau = self.r1 * self.c1
        import math
        alpha = math.exp(-dt_s / tau) if tau > 0 else 0.0
        self.v1 = self.v1 * alpha + self.r1 * current_a * (1 - alpha)
        return ocv(self.soc, self.soc_pts, self.ocv_pts) - current_a * self.r0 - self.v1


SCENARIOS = {
    "normal": {"label": "Normal", "color": "#59F2A0",
               "desc": "Pack sain, aucune anomalie detectee."},
    "desequilibre": {"label": "Desequilibre cellulaire", "color": "#F5B942",
                      "desc": "Une cellule diverge des autres en tension."},
    "emballement": {"label": "Emballement thermique", "color": "#FF5C4D",
                     "desc": "Temperature en hausse rapide et incontrolee."},
    "surtension": {"label": "Surtension de charge", "color": "#FF9F4D",
                    "desc": "Depassement du seuil de charge sur une cellule."},
    "resistance": {"label": "Resistance anormale", "color": "#FF7A6E",
                    "desc": "Chute de tension excessive sous charge."},
}

# mapping scenario cle interne (demo) -> label reel utilise par le modele entraine
SCENARIO_TO_MODEL_LABEL = {
    "normal": "normal",
    "desequilibre": "desequilibre_cellulaire",
    "emballement": "emballement_thermique",
    "surtension": "surtension_charge",
    "resistance": "resistance_anormale",
}


class LiveSimulator:
    """Genere une lecture par appel a step(), pilotee par le scenario actif (demo)."""

    def __init__(self, chemistry: str = "liion"):
        self.chemistry = chemistry
        profile = CHEMISTRIES[chemistry]
        self.v_min = profile["v_min"]
        self.v_max = profile["v_max"]
        self.cells = [
            Cell(CAPACITY_NOMINAL_AH, R0_NOMINAL, soc=0.75,
                 soc_pts=profile["soc_pts"], ocv_pts=profile["ocv_pts"])
            for _ in range(NUM_CELLS)
        ]
        self.temp = 25.0
        self.t = 0
        self.scenario = "normal"

        # --- AutoBalance (equilibrage passif par resistance de derivation) ---
        self.autobalance_enabled = True
        self.balance_turn_on = profile["default_overvoltage"] - 0.20
        self.balancing_precision = 0.03
        self.balance_bleed_rate = 0.015  # V/tick derives sur une cellule en equilibrage

        # --- Vieillissement / SOH (State of Health) ---
        # Modele simplifie a but pedagogique (pas calibre sur donnees reelles) :
        # perte = usure calendaire fixe + usure liee au debit (C-rate) + stress thermique
        # + stress supplementaire si un scenario de defaut est actif. Constantes choisies
        # pour rendre l'effet visible sur une session de demo (dizaines de ticks), pas pour
        # refleter un taux de vieillissement reel (qui se compte en mois/annees).
        self.soh = 100.0

    def set_autobalance(self, enabled: bool):
        self.autobalance_enabled = enabled

    def set_balance_params(self, turn_on: float, precision: float):
        self.balance_turn_on = turn_on
        self.balancing_precision = precision

    def set_chemistry(self, chemistry: str):
        """Change la chimie a chaud : recharge la courbe OCV et la plage de tension,
        conserve le SOC actuel des cellules (juste la tension correspondante change,
        comme si on rebranchait un pack d'une autre chimie sur le meme BMS)."""
        profile = CHEMISTRIES[chemistry]
        self.chemistry = chemistry
        self.v_min = profile["v_min"]
        self.v_max = profile["v_max"]
        for cell in self.cells:
            cell.soc_pts = profile["soc_pts"]
            cell.ocv_pts = profile["ocv_pts"]
            cell.v1 = 0.0  # reset de la dynamique RC (R0/R1 differents par chimie en realite)

    def set_scenario(self, scenario: str):
        self.scenario = scenario

    def step(self):
        self.t += 1
        charging = self.scenario == "surtension"
        if charging:
            current = -4.0 + random.uniform(-0.2, 0.2)
        else:
            import math
            current = 6.0 + 3.0 * math.sin(self.t / 6.0) + random.uniform(-0.6, 0.6)

        voltages = []
        for i, cell in enumerate(self.cells):
            v = cell.step(current)
            if self.scenario == "desequilibre" and i == FAULT_CELL_IMBALANCE:
                v -= 0.30
            if self.scenario == "resistance" and i == FAULT_CELL_RESISTANCE:
                v -= abs(current) * 0.012 * 5.0
            if self.scenario == "surtension" and i == FAULT_CELL_OVERVOLT and random.random() < 0.15:
                v += 0.28
            voltages.append(max(self.v_min - 0.4, min(self.v_max + 0.15, v)))

        # --- AutoBalance : resistance de derivation passive. Chaque cellule qui depasse
        # le seuil de declenchement ET s'ecarte de la moyenne du pack est "saignee"
        # progressivement (comme un vrai circuit de balancing resistif). Une cellule
        # FAIBLE (sous-tension) n'est jamais corrigee par ce mecanisme -- c'est realiste :
        # le balancing passif ne peut que limiter les cellules hautes, pas recharger une
        # cellule faible. ---
        balancing_indices = []
        if self.autobalance_enabled:
            v_avg = sum(voltages) / len(voltages)
            for i in range(len(voltages)):
                if voltages[i] > self.balance_turn_on and (voltages[i] - v_avg) > self.balancing_precision:
                    bleed = min(self.balance_bleed_rate, voltages[i] - v_avg)
                    voltages[i] -= bleed
                    balancing_indices.append(i)

        ambient = 25.0
        heat = 0.15 * abs(current)
        cooling = 0.35
        if self.scenario == "emballement":
            cooling = 0.05
            heat *= 3.2
        if self.scenario == "resistance":
            heat *= 1.6
        self.temp += (heat - cooling * (self.temp - ambient)) * 0.15
        self.temp = max(ambient - 2, min(140, self.temp))

        # --- Degradation SOH pour ce tick ---
        c_rate = abs(current) / CAPACITY_NOMINAL_AH
        calendar_wear = 0.0005
        usage_wear = 0.02 * c_rate
        thermal_stress = max(0.0, self.temp - 30.0) * 0.002
        fault_stress = 0.05 if self.scenario in ("emballement", "surtension", "resistance") else 0.0
        soh_loss = calendar_wear + usage_wear + thermal_stress + fault_stress
        self.soh = max(0.0, self.soh - soh_loss)

        return {
            "cell_v": voltages, "current_a": current, "temp_c": self.temp,
            "balancing_indices": balancing_indices, "soh": self.soh,
        }
