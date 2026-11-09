"""
GenerarSitemap.py  (Rompecabezas de Guatemala v9)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Lee el catálogo publicado de Google Sheets (o un CSV local) y
genera ../sitemap.xml con:
  • la página de inicio y la de privacidad
  • una URL por categoría       → https://shop.rompecabezas.online/?cat=animales
  • una URL por subcategoría    → https://shop.rompecabezas.online/?cat=<categoria>&sub=<subcategoria> (solo si la categoría tiene varias)

Los nombres en la URL ("slugs") se calculan EXACTAMENTE igual que en
js/app.js, así que siempre coinciden con lo que abre el sitio.

Uso (desde la carpeta process):
    python GenerarSitemap.py                     ← usa el Google Sheet publicado
    python GenerarSitemap.py ..\\data\\archivo.csv ← usa un CSV local

Correrlo cada vez que agregues, quites o renombres categorías,
y volver a subir sitemap.xml al hosting.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# ── CONFIGURACIÓN ─────────────────────────────────────────────────────────────
CSV_URL   = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSF1IBRN7QT8W2CsR8MvcW9x-Psy3R61mePJ0UvLEbL0GQMOAYNenr3BvYwzGKfue7x4Rc17Qzpvv8D/pub?output=csv"
URL_SITIO = "https://shop.rompecabezas.online/"
INCLUIR_SUBCATEGORIAS = True
# Columnas (posición, igual que en js/app.js): 0=id, 4=categoria_id, 5=categoria_nombre, 7=subcategoria_nombre
COL_ID, COL_CAT_ID, COL_CAT_NOMBRE, COL_SUB = 0, 4, 5, 7
# ──────────────────────────────────────────────────────────────────────────────

import csv
import io
import os
import re
import sys
import unicodedata
import urllib.request
from datetime import date
from xml.sax.saxutils import escape

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, "..", "sitemap.xml")


def slugify(texto):
    """Misma regla que slugify() en js/app.js."""
    t = unicodedata.normalize("NFD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower().strip()
    t = re.sub(r"[^a-z0-9]+", "-", t)
    return t.strip("-")


def leer_csv(origen):
    if origen.startswith("http"):
        print(f"📥 Descargando catálogo publicado…")
        with urllib.request.urlopen(origen, timeout=60) as r:
            texto = r.read().decode("utf-8-sig")
    else:
        print(f"📄 Leyendo {origen}")
        with open(origen, encoding="utf-8-sig") as f:
            texto = f.read()
    filas = list(csv.reader(io.StringIO(texto)))
    return [[c.strip() for c in fila] for fila in filas[1:]]


def main():
    origen = sys.argv[1] if len(sys.argv) > 1 else CSV_URL
    filas = leer_csv(origen)

    # Agrupar igual que iniciarApp() en js/app.js
    categorias = {}
    for f in filas:
        if len(f) <= COL_SUB or not f[COL_ID] or not f[COL_CAT_ID]:
            continue
        cid = f[COL_CAT_ID]
        cat = categorias.setdefault(cid, {"id": cid, "nombre": f[COL_CAT_NOMBRE] or cid, "subs": set(), "n": 0})
        cat["n"] += 1
        if f[COL_SUB]:
            cat["subs"].add(f[COL_SUB])

    usados = set()
    hoy = date.today().isoformat()
    urls = [
        (URL_SITIO, "daily", "1.0"),
        (URL_SITIO + "politicas", "monthly", "0.4"),
        (URL_SITIO + "privacidad", "yearly", "0.3"),
    ]
    total_subs = 0
    for cat in sorted(categorias.values(), key=lambda c: c["id"]):
        slug = slugify(cat["nombre"]) or slugify(cat["id"]) or "categoria"
        base, n = slug, 2
        while slug in usados:
            slug = f"{base}-{n}"; n += 1
        usados.add(slug)
        urls.append((f"{URL_SITIO}?cat={slug}", "weekly", "0.8"))
        print(f"  ✔ {cat['nombre']:<40} ?cat={slug}  ({cat['n']} productos)")

        subs = sorted(cat["subs"])
        # Igual que el sitio: si la única subcategoría se llama como la categoría, no tiene página propia
        # Solo vale la pena una URL por subcategoría si la categoría tiene 2 o más (si tiene una sola,
        # como "No aplica", es la misma página que la categoría)
        if INCLUIR_SUBCATEGORIAS and len(subs) > 1:
            for sub in subs:
                urls.append((f"{URL_SITIO}?cat={slug}&sub={slugify(sub)}", "weekly", "0.6"))
                total_subs += 1

    lineas = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, freq, prio in urls:
        lineas.append(f"  <url><loc>{escape(loc)}</loc><lastmod>{hoy}</lastmod>"
                      f"<changefreq>{freq}</changefreq><priority>{prio}</priority></url>")
    lineas.append("</urlset>")

    with open(SALIDA, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lineas) + "\n")

    print(f"\n✅ sitemap.xml generado: {len(categorias)} categorías, {total_subs} subcategorías, {len(urls)} URLs en total.")
    print(f"   {os.path.normpath(SALIDA)}")
    print("   Súbelo al hosting y, si quieres, avísale a Google en Search Console → Sitemaps.")


if __name__ == "__main__":
    main()
