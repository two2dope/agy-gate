"""Gera o ícone do app (assets/app.ico e assets/app-<tamanho>.png) com o Pillow. Uso: python tools/make_icon.py [pasta de saída].
Desenho: um portal em arco (o "gate") com 3 barras de nível dentro (verde, âmbar e vermelho: o medidor de contexto), sobre o azul-preto do tema Dark Alloy."""
import os
import sys
from PIL import Image, ImageDraw

S = 1024
BG, EDGE, ARCH = "#0c0f17", "#1e263d", "#38bdf8"
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
os.makedirs(out, exist_ok=True)

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((32, 32, S - 32, S - 32), radius=210, fill=BG, outline=EDGE, width=10)
d.ellipse((252, 190, 772, 710), fill=ARCH)            # arco externo
d.rectangle((252, 450, 772, 830), fill=ARCH)          # pilares
d.ellipse((328, 266, 696, 634), fill=BG)              # vão do arco
d.rectangle((328, 450, 696, 840), fill=BG)            # vão dos pilares, aberto embaixo
for y, color in ((700, "#34d399"), (590, "#fbbf24"), (480, "#f43f5e")):
    d.rounded_rectangle((372, y, 652, y + 70), radius=35, fill=color)
sizes = (16, 24, 32, 48, 64, 128, 256)
img.save(os.path.join(out, "app.ico"), sizes=[(s, s) for s in sizes])
for s in (256, 64, 32):
    img.resize((s, s), Image.LANCZOS).save(os.path.join(out, f"app-{s}.png"))
print("ok:", sorted(os.listdir(out)))
