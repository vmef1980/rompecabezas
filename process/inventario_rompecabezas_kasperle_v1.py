# ==============================================================================
# VERSIÓN 1: SCRIPT DE EXTRACCIÓN DE DATOS PARA KASPERLE
# ==============================================================================
# Basado en el script de DEMUSEO v1, adaptado a https://www.kasperle.com
#
# Cómo funciona Kasperle (analizado):
#   - Listado:   /shop?q=rompecabezas&page=N  (HTML renderizado en servidor).
#                Cada tarjeta trae un atributo data-ga-select con JSON:
#                {"item": {"item_id": SKU, "item_name": titulo, "price": precio}}
#   - Producto:  /p/<slug>  -> JSON-LD (schema.org Product) con imagen, marca,
#                breadcrumb y disponibilidad en línea; descripción en el HTML.
#   - APIs JSON (no requieren sesión ni cookies):
#       /api/stock/{SKU}      -> stock por tienda:
#                                [{storeName, city, status, qty}, ...]
#                                status: in_stock | low_stock | out_of_stock
#       /api/available/{SKU}  -> {"qty": n}  unidades para venta en línea
#       /api/live-price/{SKU} -> {"price": x, "special": y|null} (precio oferta)
#   Por eso NO se usa Selenium: requests + BeautifulSoup es más rápido y estable.
#
# Columnas del CSV (mismas que DEMUSEO v1 + 1 nueva al final):
#    id, titulo, imagen, imagenes, categoria_id, categoria_nombre,
#    subcategoria_id, subcategoria_nombre, producto_descripcion, precio,
#    estado, precio_original, sku, empresa,
#    disponibilidad_tiendas   <-- NUEVA: "Tienda (Ciudad): Estado | ..."
#
# Requisitos:  pip install requests beautifulsoup4
# ==============================================================================

import csv, json, math, os, re, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

import requests
from bs4 import BeautifulSoup

BASE = "https://www.kasperle.com"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
    "Accept-Language": "es-GT,es;q=0.9",
}
MAX_PAGINAS = 60          # tope de seguridad; se detiene solo al no haber productos
HILOS = 5                 # peticiones simultáneas (moderado para no saturar el sitio)

ESTADOS_TIENDA = {
    "in_stock": "Disponible",
    "low_stock": "Pocas unidades",
    "out_of_stock": "Agotado",
}

_local = threading.local()


def sesion():
    """Una sesión de requests por hilo."""
    if not hasattr(_local, "s"):
        s = requests.Session()
        s.headers.update(HEADERS)
        _local.s = s
    return _local.s


def get(url, como_json=False, reintentos=3):
    for intento in range(reintentos):
        try:
            r = sesion().get(url, timeout=20)
            if r.status_code == 200:
                return r.json() if como_json else r.text
            if r.status_code == 404:
                return None
        except (requests.RequestException, ValueError):
            pass
        time.sleep(1.5 * (intento + 1))
    return None


# ------------------------------------------------------------------------------
# Categoría (misma lógica que DEMUSEO, ampliada para formatos de Kasperle
# como "15p", "2000P", "48 Pzs" y usando el breadcrumb para detectar 3D)
# ------------------------------------------------------------------------------
PIEZAS_COMUNES = {12, 15, 24, 30, 35, 48, 50, 60, 99, 100, 150, 200, 250, 300,
                  500, 1000, 1200, 1500, 2000, 3000, 4000, 5000, 6000, 9000,
                  13200, 18000, 32000, 40000}


def analizar_categoria(titulo, breadcrumb=""):
    t = titulo.upper()
    b = breadcrumb.upper()

    # 1. Rompecabezas 3D (por título o por categoría del sitio)
    if re.search(r'\b3D\b', t) or "ROMPECABEZAS 3D" in b:
        return "rompecabezas_3d", "Rompecabezas 3D", "rompecabezas_3d", "Rompecabezas 3D"

    # 2. Número con sufijo explícito de piezas (1000 PIEZAS, 48 PZS, 15P, 2000P...)
    m = re.search(r'\b(\d{1,5})\s*(?:PIEZAS|PIEZA|PZS|PZAS|PCS|PZ|P)\b', t)
    if m:
        num = int(m.group(1))
        if num >= 2:
            return f"{num}_piezas", f"{num} piezas", f"{num}_piezas", f"{num} piezas"

    # 3. Número suelto que coincida con un conteo de piezas habitual
    #    (evita códigos del fabricante como 179015 o 12001335)
    for n in re.findall(r'\b\d+\b', t):
        val = int(n)
        if val in PIEZAS_COMUNES:
            return f"{val}_piezas", f"{val} piezas", f"{val}_piezas", f"{val} piezas"

    return "general", "General", "general", "General"


# ------------------------------------------------------------------------------
# Extracción
# ------------------------------------------------------------------------------
def leer_listado(url_busqueda, pagina):
    sep = "&" if "?" in url_busqueda else "?"
    html = get(f"{url_busqueda}{sep}page={pagina}")
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    productos, vistos = [], set()
    for a in soup.select("a[data-ga-select]"):
        try:
            item = json.loads(a["data-ga-select"])["item"]
        except (KeyError, ValueError):
            continue
        sku = item.get("item_id")
        href = a.get("href", "")
        if not sku or sku in vistos or "/p/" not in href:
            continue
        vistos.add(sku)
        productos.append({
            "sku": sku,
            "titulo": item.get("item_name", "").strip(),
            "precio": item.get("price"),
            "url": BASE + href if href.startswith("/") else href,
        })
    return productos


def leer_detalle(prod):
    """Página de producto: imagen, descripción y breadcrumb."""
    imagen, descripcion, breadcrumb = "", "", ""
    html = get(prod["url"])
    if html:
        soup = BeautifulSoup(html, "html.parser")
        for s in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(s.string or "")
            except ValueError:
                continue
            tipo = data.get("@type")
            if tipo == "Product":
                imgs = data.get("image") or []
                if isinstance(imgs, str):
                    imgs = [imgs]
                if imgs:
                    imagen = imgs[0]
                if data.get("description"):
                    descripcion = data["description"].strip()
            elif tipo == "BreadcrumbList":
                breadcrumb = " > ".join(
                    i.get("name", "") for i in data.get("itemListElement", []))

        if not descripcion:
            p = soup.select_one(".bajo-el-fold p.leading-relaxed")
            if p and p.get_text(strip=True):
                descripcion = p.get_text(" ", strip=True)
        if not imagen:
            og = soup.select_one('meta[property="og:image"]')
            img = soup.select_one('img[src*="/catalog/"]')
            imagen = (img["src"] if img else "") or (og["content"] if og else "")

    return imagen, (descripcion or prod["titulo"]), breadcrumb


def leer_disponibilidad(sku):
    """Devuelve (texto_por_tienda, tiendas_con_stock, unidades_en_linea)."""
    stock = get(f"{BASE}/api/stock/{sku}", como_json=True) or {}
    disp = get(f"{BASE}/api/available/{sku}", como_json=True) or {}
    en_linea = disp.get("qty") or 0

    partes, con_stock = [], 0
    for t in stock.get("stock", []):
        status = t.get("status", "")
        nombre = t.get("storeName", t.get("storeCode", "?")).replace("Kasperle ", "")
        lugar = f"{nombre} ({t.get('city', '')})" if t.get("city") else nombre
        texto = ESTADOS_TIENDA.get(status, status)
        if status == "low_stock" and t.get("qty"):
            texto += f" ({t['qty']})"
        if status != "out_of_stock":
            con_stock += 1
        partes.append(f"{lugar}: {texto}")

    if not partes:
        return "Sin información", con_stock, en_linea

    # Mismo resumen que muestra la página: "Disponible hoy en 11 tiendas"
    if con_stock:
        resumen = f"Disponible hoy en {con_stock} tienda{'s' if con_stock != 1 else ''}"
    else:
        resumen = "No disponible en tiendas"
    if en_linea:
        resumen += f" · En línea: {en_linea} unid."
    return resumen + " · " + " | ".join(partes), con_stock, en_linea


def leer_precio_oferta(sku):
    lp = get(f"{BASE}/api/live-price/{sku}", como_json=True) or {}
    return lp.get("special")


def procesar_producto(prod, costo_adicional, pct_ganancia):
    imagen, descripcion, breadcrumb = leer_detalle(prod)
    texto_disp, con_stock, en_linea = leer_disponibilidad(prod["sku"])

    precio_orig = float(prod["precio"] or 0)
    oferta = leer_precio_oferta(prod["sku"])
    if oferta:
        precio_orig = float(oferta)
    precio_sugerido = math.ceil(precio_orig + costo_adicional + precio_orig * pct_ganancia)

    estado = "DISPONIBLE" if (con_stock > 0 or en_linea > 0) else "AGOTADO"
    cat_id, cat_nom, sub_id, sub_nom = analizar_categoria(prod["titulo"], breadcrumb)

    return [
        f"KS{prod['sku']}", prod["titulo"], imagen, imagen,
        cat_id, cat_nom, sub_id, sub_nom,
        descripcion, precio_sugerido, estado,
        precio_orig, prod["sku"], "KASPERLE",
        texto_disp,
    ]


ENCABEZADOS = [
    "id", "titulo", "imagen", "imagenes",
    "categoria_id", "categoria_nombre", "subcategoria_id", "subcategoria_nombre",
    "producto_descripcion", "precio", "estado", "precio_original", "sku", "empresa",
    "disponibilidad_tiendas",
]


def iniciar_scraping(ui):
    def ui_set(var, valor):
        root.after(0, var.set, valor)

    def log(msg):
        def _w():
            ui["log"].insert(tk.END, msg + "\n")
            ui["log"].see(tk.END)
        root.after(0, _w)

    archivo = ui["archivo"].get()
    url_busqueda = ui["url"].get().strip()
    try:
        costo = float(ui["reco"].get())
        pct = float(ui["gana"].get()) / 100
    except ValueError:
        root.after(0, lambda: messagebox.showerror("Error", "Costo y Ganancia deben ser números."))
        return

    carpeta = os.path.dirname(archivo)
    if carpeta and not os.path.exists(carpeta):
        os.makedirs(carpeta)

    root.after(0, lambda: ui["boton"].config(state="disabled"))
    try:
        # 1. Recorrer el listado
        productos, vistos = [], set()
        for pag in range(1, MAX_PAGINAS + 1):
            ui_set(ui["titulo"], f"Leyendo listado, página {pag}...")
            lote = [p for p in leer_listado(url_busqueda, pag) if p["sku"] not in vistos]
            if not lote:
                break
            for p in lote:
                vistos.add(p["sku"])
            productos.extend(lote)
            log(f"[LISTADO] Página {pag}: {len(lote)} productos (total {len(productos)})")
            time.sleep(0.5)

        if not productos:
            root.after(0, lambda: messagebox.showwarning("Sin datos", "No se encontraron productos."))
            return

        # 2. Detalle + disponibilidad por tienda (en paralelo)
        datos, totales = [], {"disp": 0, "agot": 0}
        with ThreadPoolExecutor(max_workers=HILOS) as ex:
            futuros = {ex.submit(procesar_producto, p, costo, pct): p for p in productos}
            for fut in as_completed(futuros):
                p = futuros[fut]
                try:
                    fila = fut.result()
                except Exception as e:
                    log(f"[ERROR] {p['sku']} | {p['titulo']} | {e}")
                    continue
                datos.append(fila)
                totales["disp" if fila[10] == "DISPONIBLE" else "agot"] += 1

                ui_set(ui["titulo"], f"Producto: {fila[1]}")
                ui_set(ui["contador"], f"Procesados: {len(datos)}/{len(productos)} "
                                       f"(Disp: {totales['disp']} | Agot: {totales['agot']})")
                ui_set(ui["detalle"], f"SKU: {fila[12]} | Cat: {fila[5]} | Precio Sug: {fila[9]}")
                log(f"[OK] SKU: {fila[12]} | {fila[1]} | Cat: {fila[5]} | "
                    f"Precio: {fila[9]} | {fila[10]}")

        # Mantener el orden del sitio
        orden = {p["sku"]: i for i, p in enumerate(productos)}
        datos.sort(key=lambda f: orden.get(f[12], 0))

        with open(archivo, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(ENCABEZADOS)
            w.writerows(datos)

        resumen = (f"Resumen Kasperle v1:\n{totales['disp']} disponibles, "
                   f"{totales['agot']} agotados.\nArchivo: {archivo}")
        root.after(0, lambda: messagebox.showinfo("Finalizado", resumen))
    finally:
        root.after(0, lambda: ui["boton"].config(state="normal"))


# --- GUI (Versión 1) ---
root = tk.Tk()
root.title("Scraper Kasperle - Versión 1")
root.geometry("760x720")

tk.Label(root, text="URL de búsqueda:").pack(pady=2)
entry_url = tk.Entry(root, width=90)
entry_url.insert(0, f"{BASE}/shop?q=rompecabezas")
entry_url.pack(pady=2)

tk.Label(root, text="Ruta CSV de Salida:").pack(pady=2)
entry_ruta = tk.Entry(root, width=90)
entry_ruta.insert(0, r"D:\Projects\2026\Development\WebPages\Rompecabezas\Rompecabezas-v7\data\catalogo_kasperle.csv")
entry_ruta.pack(pady=2)

tk.Label(root, text="Costo Recolección:").pack(pady=2)
entry_reco = tk.Entry(root, width=15)
entry_reco.insert(0, "15.0")
entry_reco.pack(pady=2)

tk.Label(root, text="% Ganancia (ej 30):").pack(pady=2)
entry_gana = tk.Entry(root, width=15)
entry_gana.insert(0, "30")
entry_gana.pack(pady=2)

var_titulo = tk.StringVar(value="Estado: En espera de inicio...")
var_contador = tk.StringVar(value="Procesados: 0")
var_detalle = tk.StringVar(value="Detalles de extracción en vivo aparecerán aquí...")

ttk.Label(root, textvariable=var_titulo, font=("Arial", 10, "bold"), foreground="navy").pack(pady=5)
ttk.Label(root, textvariable=var_contador, font=("Arial", 9)).pack(pady=2)
ttk.Label(root, textvariable=var_detalle, font=("Arial", 9, "italic"), foreground="darkgreen").pack(pady=2)

log_area = scrolledtext.ScrolledText(root, width=88, height=15)
log_area.pack(pady=10)

btn = tk.Button(root, text="INICIAR PROCESO (Kasperle v1)", bg="#C2392F", fg="white",
                font=("Arial", 10, "bold"))
btn.pack(pady=10)

UI = {
    "url": entry_url, "archivo": entry_ruta, "reco": entry_reco, "gana": entry_gana,
    "titulo": var_titulo, "contador": var_contador, "detalle": var_detalle,
    "log": log_area, "boton": btn,
}
btn.config(command=lambda: threading.Thread(target=iniciar_scraping, args=(UI,), daemon=True).start())

root.mainloop()
