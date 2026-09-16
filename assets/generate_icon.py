"""
Genere une icone d'application placeholder (icon.ico + icon.png) pour Smart BMS.
A remplacer par un vrai logo Akkurad si disponible -- ceci est un point de depart
propre (pack de batterie stylise + eclair), pas un logo definitif.

Lancer une seule fois : python assets/generate_icon.py
"""

from PIL import Image, ImageDraw

BG = (11, 15, 13, 255)
GREEN = (89, 242, 160, 255)
COPPER = (217, 142, 74, 255)
BORDER = (28, 38, 32, 255)

SIZE = 256


def build_icon():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fond arrondi
    draw.rounded_rectangle([8, 8, SIZE - 8, SIZE - 8], radius=48, fill=BG, outline=BORDER, width=4)

    # Corps de la cellule (rectangle vertical arrondi, style banc de cellules du dashboard)
    cell_w, cell_h = 92, 150
    cx, cy = SIZE // 2, SIZE // 2 + 10
    x0, y0 = cx - cell_w // 2, cy - cell_h // 2
    x1, y1 = cx + cell_w // 2, cy + cell_h // 2
    draw.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=GREEN)

    # Petite borne (terminal) en haut, style cuivre
    term_w, term_h = 30, 14
    draw.rounded_rectangle(
        [cx - term_w // 2, y0 - term_h + 4, cx + term_w // 2, y0 + 6], radius=4, fill=COPPER
    )

    # Eclair (diagnostic / energie) decoupe en transparence dans la cellule
    bolt = [
        (cx + 14, y0 + 18), (cx - 10, cy + 6), (cx + 4, cy + 6),
        (cx - 14, y1 - 14), (cx + 18, cy - 10), (cx + 2, cy - 10),
    ]
    draw.polygon(bolt, fill=BG)

    return img


if __name__ == "__main__":
    icon = build_icon()
    icon.save("assets/icon.png")
    icon.save("assets/icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Icone generee : assets/icon.png + assets/icon.ico")
