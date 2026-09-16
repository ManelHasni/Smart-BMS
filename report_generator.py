"""
Generateur de rapport PDF — pense pour un ouvrier/operateur sans connaissance technique.
Langage simple, gros visuels (jauges circulaires, barres), une consigne claire par etat.
"""

from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = A4

PLAIN = {
    "normal": {
        "mot": "OK",
        "titre": "Batterie en bon etat",
        "phrase": "Toutes les mesures sont dans les valeurs normales. Aucune anomalie detectee.",
        "consigne": "Aucune action requise. Utilisation normale possible.",
        "couleur": "#1E9E5A",
    },
    "desequilibre_cellulaire": {
        "mot": "SURVEILLANCE",
        "titre": "Une cellule de la batterie vieillit plus vite que les autres",
        "phrase": "Une des 10 cellules a une tension differente des autres. C'est un signe "
                   "d'usure inegale, pas un danger immediat.",
        "consigne": "Faire verifier la batterie par la maintenance dans les prochains jours.",
        "couleur": "#C98A1E",
    },
    "emballement_thermique": {
        "mot": "DANGER",
        "titre": "Temperature anormalement elevee, en hausse rapide",
        "phrase": "La batterie chauffe beaucoup plus que la normale et la temperature continue "
                   "de monter. C'est un signe de danger.",
        "consigne": "ARRETER l'utilisation immediatement. Poser la batterie dans un endroit sur, "
                     "loin de matieres inflammables. Prevenir la maintenance en urgence.",
        "couleur": "#D8412E",
    },
    "surtension_charge": {
        "mot": "ALERTE",
        "titre": "Le chargeur envoie trop de tension a une cellule",
        "phrase": "Une cellule a recu plus de tension que ce qui est autorise pendant la charge. "
                   "Le chargeur ou le systeme de regulation a un probleme.",
        "consigne": "Debrancher le chargeur. Ne pas recharger avant verification par la "
                     "maintenance.",
        "couleur": "#D8722E",
    },
    "resistance_anormale": {
        "mot": "ALERTE",
        "titre": "Une cellule perd anormalement de tension a l'effort",
        "phrase": "Une cellule chute beaucoup plus que les autres quand on sollicite la "
                   "batterie. C'est souvent le signe avant-coureur d'une panne interne.",
        "consigne": "Eviter les efforts intenses avec cette batterie. Planifier un controle "
                     "avant qu'elle ne se degrade davantage.",
        "couleur": "#D8412E",
    },
}


def _color(hexval):
    return colors.HexColor(hexval)


def _draw_ring_gauge(c, cx, cy, r, pct, color_hex, center_text, sub_text, center_font=26):
    pct = max(0.0, min(100.0, pct))
    c.setFillColor(_color("#EAEAEA"))
    c.circle(cx, cy, r, stroke=0, fill=1)

    extent = -360.0 * (pct / 100.0)
    c.setFillColor(_color(color_hex))
    c.wedge(cx - r, cy - r, cx + r, cy + r, 90, extent, stroke=0, fill=1)

    inner_r = r * 0.62
    c.setFillColor(colors.white)
    c.circle(cx, cy, inner_r, stroke=0, fill=1)

    c.setFillColor(_color("#222222"))
    c.setFont("Helvetica-Bold", center_font)
    c.drawCentredString(cx, cy - center_font * 0.35, center_text)
    if sub_text:
        c.setFont("Helvetica", 9)
        c.setFillColor(_color("#666666"))
        c.drawCentredString(cx, cy - r - 14, sub_text)


def _draw_cell_bars(c, x, y, w, h, voltages, fault_index, fault_color_hex, v_min=3.0, v_max=4.2):
    n = len(voltages)
    slot_w = w / n
    bar_w = slot_w * 0.55
    c.setFont("Helvetica", 7)
    for i, v in enumerate(voltages):
        cx = x + slot_w * i + slot_w / 2
        pct = max(0.0, min(1.0, (v - v_min) / (v_max - v_min)))
        bar_h = h * pct
        is_fault = (i == fault_index)
        color = _color(fault_color_hex) if is_fault else _color("#3CA873")

        c.setFillColor(_color("#E5E5E5"))
        c.roundRect(cx - bar_w / 2, y, bar_w, h, 2, stroke=0, fill=1)

        c.setFillColor(color)
        c.roundRect(cx - bar_w / 2, y, bar_w, bar_h, 2, stroke=0, fill=1)

        c.setFillColor(_color("#333333"))
        c.drawCentredString(cx, y + h + 6, f"{v:.2f}V")
        c.setFillColor(_color("#888888"))
        c.drawCentredString(cx, y - 12, f"C{i+1}")


def _draw_confidence_bar(c, x, y, w, h, pct, color_hex):
    c.setFillColor(_color("#E5E5E5"))
    c.roundRect(x, y, w, h, h / 2, stroke=0, fill=1)
    fill_w = w * max(0.0, min(1.0, pct / 100.0))
    if fill_w > h:
        c.setFillColor(_color(color_hex))
        c.roundRect(x, y, fill_w, h, h / 2, stroke=0, fill=1)
    c.setFillColor(_color("#222222"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x + w + 10, y + h / 2 - 4, f"{pct:.0f}%")


def _draw_probability_bars(c, x, y, w, row_h, probabilities: dict):
    labels_fr = {
        "normal": "Normal",
        "desequilibre_cellulaire": "Desequilibre cellulaire",
        "emballement_thermique": "Emballement thermique",
        "surtension_charge": "Surtension de charge",
        "resistance_anormale": "Resistance anormale",
    }
    order = ["normal", "desequilibre_cellulaire", "emballement_thermique",
             "surtension_charge", "resistance_anormale"]
    label_w = 150
    bar_w = w - label_w - 45
    c.setFont("Helvetica", 9)
    for i, key in enumerate(order):
        yy = y - i * row_h
        p = probabilities.get(key, 0.0) * 100
        c.setFillColor(_color("#333333"))
        c.drawString(x, yy, labels_fr[key])
        c.setFillColor(_color("#EAEAEA"))
        c.roundRect(x + label_w, yy - 3, bar_w, 10, 5, stroke=0, fill=1)
        c.setFillColor(_color(PLAIN[key]["couleur"]))
        fw = bar_w * p / 100.0
        if fw > 10:
            c.roundRect(x + label_w, yy - 3, fw, 10, 5, stroke=0, fill=1)
        c.setFillColor(_color("#333333"))
        c.drawString(x + label_w + bar_w + 8, yy, f"{p:.0f}%")


def _draw_page1_diagnostic(c, snapshot: dict):
    """
    snapshot attendu :
        label, confidence, probabilities (dict), pack_v, current, temp,
        soc, soh, cell_voltages (list[10]), fault_index (int|None)
    """
    info = PLAIN.get(snapshot["label"], PLAIN["normal"])
    color_hex = info["couleur"]

    # --- Bandeau d'en-tete colore ---
    c.setFillColor(_color(color_hex))
    c.rect(0, PAGE_H - 90, PAGE_W, 90, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, PAGE_H - 45, "RAPPORT DE DIAGNOSTIC")
    c.setFont("Helvetica", 11)
    c.drawString(40, PAGE_H - 65, "Smart BMS — Pack LiPo 10S / 36V — micro-mobilite electrique")
    status_font = 16 if len(info["mot"]) <= 8 else 12
    c.setFont("Helvetica-Bold", status_font)
    c.drawRightString(PAGE_W - 40, PAGE_H - 45, info["mot"])

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    c.setFillColor(_color("#666666"))
    c.setFont("Helvetica", 9)
    c.drawString(40, PAGE_H - 105, f"Rapport genere le {now_str}")

    # --- Jauge d'etat general + explication en langage simple ---
    gauge_cy = PAGE_H - 220
    _draw_ring_gauge(c, 110, gauge_cy, 60, 100, color_hex, info["mot"], "Etat general", center_font=15)

    text_x = 220
    c.setFillColor(_color("#111111"))
    c.setFont("Helvetica-Bold", 14)
    c.drawString(text_x, PAGE_H - 165, info["titre"])

    c.setFont("Helvetica", 10.5)
    c.setFillColor(_color("#333333"))
    from textwrap import wrap
    lines = wrap(info["phrase"], 62)
    yy = PAGE_H - 185
    for line in lines:
        c.drawString(text_x, yy, line)
        yy -= 14

    # boite consigne
    box_y = yy - 16
    c.setFillColor(_color("#FFF7EC") if color_hex != "#1E9E5A" else _color("#EAFBF1"))
    c.roundRect(text_x, box_y - 40, PAGE_W - text_x - 40, 44, 6, stroke=0, fill=1)
    c.setFillColor(_color(color_hex))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(text_x + 10, box_y - 14, "CE QU'IL FAUT FAIRE :")
    c.setFillColor(_color("#222222"))
    c.setFont("Helvetica", 10)
    for i, line in enumerate(wrap(info["consigne"], 68)):
        c.drawString(text_x + 10, box_y - 28 - i * 12, line)

    row1_bottom = min(gauge_cy - 60 - 14, box_y - 40)

    # --- Metriques cles (SOC, SOH, tension, courant, temperature) ---
    metrics_y = row1_bottom - 75
    _draw_ring_gauge(c, 100, metrics_y, 42, snapshot["soc"], "#3CA873", f"{snapshot['soc']:.0f}%", "SOC (charge)", center_font=13)
    _draw_ring_gauge(c, 210, metrics_y, 42, snapshot["soh"], "#C98A1E", f"{snapshot['soh']:.0f}%", "SOH (sante)", center_font=13)

    metric_x = 300
    c.setFont("Helvetica", 9)
    c.setFillColor(_color("#666666"))
    labels = ["Tension pack", "Courant", "Temperature"]
    values = [f"{snapshot['pack_v']:.1f} V", f"{snapshot['current']:.1f} A", f"{snapshot['temp']:.0f} \u00b0C"]
    for i, (lab, val) in enumerate(zip(labels, values)):
        yy = metrics_y + 28 - i * 26
        c.setFillColor(_color("#666666"))
        c.setFont("Helvetica", 9)
        c.drawString(metric_x, yy, lab)
        c.setFillColor(_color("#111111"))
        c.setFont("Helvetica-Bold", 13)
        c.drawString(metric_x + 120, yy - 3, val)

    row2_bottom = metrics_y - 42 - 14

    # --- Banc de cellules ---
    bars_h = 60
    cells_y = row2_bottom - 60 - bars_h
    c.setFillColor(_color("#111111"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, cells_y + bars_h + 24, "Tension de chaque cellule (pack 10S)")
    _draw_cell_bars(c, 40, cells_y, PAGE_W - 80, bars_h, snapshot["cell_voltages"],
                     snapshot.get("fault_index"), color_hex)

    row3_bottom = cells_y - 12

    # --- Repartition des probabilites ---
    proba_row_h = 20
    proba_y = row3_bottom - 40
    c.setFillColor(_color("#111111"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, proba_y + 20, "Analyse detaillee du modele (probabilite par type de defaut)")
    _draw_probability_bars(c, 40, proba_y, PAGE_W - 80, proba_row_h, snapshot["probabilities"])

    row4_bottom = proba_y - 4 * proba_row_h

    # --- Confiance globale ---
    conf_y = row4_bottom - 40
    c.setFillColor(_color("#111111"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, conf_y + 18, "Confiance du diagnostic")
    _draw_confidence_bar(c, 40, conf_y, 300, 14, snapshot["confidence"] * 100, color_hex)

    # --- Pied de page ---
    c.setFillColor(_color("#999999"))
    c.setFont("Helvetica", 8)
    c.drawString(40, 30, "Rapport genere automatiquement par Smart BMS (modele Random Forest entraine hors-ligne).")
    c.drawString(40, 18, "En cas de doute, contacter le service maintenance avant toute utilisation.")


def generate_pdf_report(filepath: str, snapshot: dict):
    """Rapport 1 page (diagnostic ponctuel) -- comportement inchange, conserve pour
    compatibilite avec le bouton 'Exporter le diagnostic (PDF)' existant."""
    c = canvas.Canvas(filepath, pagesize=A4)
    _draw_page1_diagnostic(c, snapshot)
    c.save()


def _page_header(c, title, subtitle, page_num, page_count):
    c.setFillColor(_color("#131A17"))
    c.rect(0, PAGE_H - 60, PAGE_W, 60, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, PAGE_H - 32, title)
    c.setFont("Helvetica", 9)
    c.setFillColor(_color("#8FA79B"))
    c.drawString(40, PAGE_H - 48, subtitle)
    c.drawRightString(PAGE_W - 40, PAGE_H - 32, f"Page {page_num}/{page_count}")
    c.setFillColor(_color("#999999"))
    c.setFont("Helvetica", 8)
    c.drawString(40, 18, "Smart BMS — Akkurad GmbH — Rapport de synthese genere automatiquement.")


def _draw_line_chart(c, x, y, w, h, xs, ys, color_hex, y_label="", x_label="",
                      threshold=None, threshold_color="#D64545"):
    """Trace un graphique en ligne simple (sans dependance externe a matplotlib),
    coherent avec le style 'trait fin' du reste du rapport."""
    c.setStrokeColor(_color("#CCCCCC"))
    c.setLineWidth(0.6)
    c.line(x, y, x, y + h)
    c.line(x, y, x + w, y)

    if not xs or not ys or len(xs) < 2:
        c.setFillColor(_color("#999999"))
        c.setFont("Helvetica-Oblique", 9)
        c.drawCentredString(x + w / 2, y + h / 2, "Pas assez de donnees pour tracer ce graphique.")
        return

    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    if threshold is not None:
        y_min = min(y_min, threshold)
    y_span = (y_max - y_min) or 1.0
    x_span = (x_max - x_min) or 1.0

    def px(v):
        return x + (v - x_min) / x_span * w

    def py(v):
        return y + (v - y_min) / y_span * h

    if threshold is not None:
        c.setStrokeColor(_color(threshold_color))
        c.setDash(3, 2)
        c.setLineWidth(0.8)
        c.line(x, py(threshold), x + w, py(threshold))
        c.setDash()
        c.setFillColor(_color(threshold_color))
        c.setFont("Helvetica", 7)
        c.drawString(x + w - 90, py(threshold) + 3, f"seuil {threshold:g}")

    c.setStrokeColor(_color(color_hex))
    c.setLineWidth(1.4)
    path = c.beginPath()
    path.moveTo(px(xs[0]), py(ys[0]))
    for xv, yv in zip(xs[1:], ys[1:]):
        path.lineTo(px(xv), py(yv))
    c.drawPath(path, stroke=1, fill=0)

    c.setFillColor(_color("#666666"))
    c.setFont("Helvetica", 7)
    c.drawString(x, y - 12, f"{x_min:.0f}")
    c.drawRightString(x + w, y - 12, f"{x_max:.0f}")
    c.drawString(x - 32, y - 3, f"{y_min:.0f}")
    c.drawString(x - 32, y + h - 6, f"{y_max:.0f}")
    if x_label:
        c.drawCentredString(x + w / 2, y - 22, x_label)
    if y_label:
        c.saveState()
        c.translate(x - 38, y + h / 2)
        c.rotate(90)
        c.drawCentredString(0, 0, y_label)
        c.restoreState()


def _draw_kv_table(c, x, y, w, rows, row_h=18, font_size=9):
    """Petit tableau cle/valeur (label a gauche, valeur alignee a droite)."""
    c.setFont("Helvetica", font_size)
    for i, (label, value) in enumerate(rows):
        yy = y - i * row_h
        c.setFillColor(_color("#555555"))
        c.drawString(x, yy, str(label))
        c.setFillColor(_color("#111111"))
        c.setFont("Helvetica-Bold", font_size)
        c.drawRightString(x + w, yy, str(value))
        c.setFont("Helvetica", font_size)
    return y - len(rows) * row_h


def generate_full_report(filepath: str, snapshot: dict, soh_history=None,
                          protection_events=None, session_data=None, device_info=None,
                          log_entries=None):
    """Rapport de synthese complet, 3 pages :
      1. Diagnostic ponctuel (identique a l'export simple)
      2. Evolution du SOH + estimation RUL + historique des declenchements
      3. Valeurs de session + infos appareil + journal recent
    """
    soh_history = soh_history or []
    protection_events = protection_events or {}
    session_data = session_data or {}
    device_info = device_info or {}
    log_entries = log_entries or []

    c = canvas.Canvas(filepath, pagesize=A4)

    # ---- Page 1 : diagnostic (reutilise telle quelle) ----
    _draw_page1_diagnostic(c, snapshot)
    c.showPage()

    # ---- Page 2 : SOH / RUL / historique des declenchements ----
    _page_header(c, "EVOLUTION SOH & DECLENCHEMENTS", "Estimation de duree de vie et historique de protection", 2, 3)

    chart_y = PAGE_H - 260
    c.setFillColor(_color("#111111"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, PAGE_H - 90, "Evolution du SOH (session en cours)")
    xs = [t for t, _ in soh_history]
    ys = [s for _, s in soh_history]
    _draw_line_chart(c, 80, chart_y, PAGE_W - 160, 140, xs, ys, "#C98A1E",
                      y_label="SOH %", x_label="tick", threshold=80, threshold_color="#D64545")

    hist_y = chart_y - 60
    c.setFillColor(_color("#111111"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, hist_y + 20, "Historique des declenchements de protection")
    EVENT_LABELS_FR = {
        "cell_overvoltage": "Surtension cellule", "cell_undervoltage": "Sous-tension cellule",
        "charge_overcurrent": "Surintensite charge", "discharge_overcurrent": "Surintensite decharge",
        "charge_over_temperature": "Surchauffe charge", "discharge_over_temperature": "Surchauffe decharge",
        "short_circuit": "Court-circuit",
    }
    rows = [(EVENT_LABELS_FR.get(k, k), v) for k, v in protection_events.items()]
    _draw_kv_table(c, 40, hist_y, PAGE_W - 80, rows, row_h=16, font_size=9)
    c.showPage()

    # ---- Page 3 : Session + infos appareil + journal ----
    _page_header(c, "SESSION & INFOS APPAREIL", "Valeurs de session, identification du pack, journal recent", 3, 3)

    c.setFillColor(_color("#111111"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, PAGE_H - 90, "Valeurs de session")
    session_rows = [(k, v) for k, v in session_data.items()]
    y_after = _draw_kv_table(c, 40, PAGE_H - 115, 260, session_rows, row_h=18, font_size=9.5)

    c.setFillColor(_color("#111111"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(320, PAGE_H - 90, "Infos appareil")
    device_rows = [(k, v) for k, v in device_info.items()]
    _draw_kv_table(c, 320, PAGE_H - 115, 220, device_rows, row_h=18, font_size=9.5)

    log_y = min(y_after, PAGE_H - 115 - len(device_rows) * 18) - 40
    c.setFillColor(_color("#111111"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, log_y + 18, "Journal (evenements recents)")
    c.setFont("Helvetica", 8.5)
    yy = log_y
    for entry in log_entries[:18]:
        c.setFillColor(_color("#444444"))
        c.drawString(40, yy, str(entry)[:110])
        yy -= 13
        if yy < 40:
            break

    c.save()

