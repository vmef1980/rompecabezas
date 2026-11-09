# ==============================================================================
# VERSIÓN 1: SCRIPT DE SCRAPING Y EXTRACCIÓN DE DATOS PARA DEMUSEO
# ==============================================================================
# Resumen de cambios y estructuración implementados en esta versión:
# 1. Nueva estructura de columnas en el archivo CSV generado:
#    - id (anteriormente id_propio, formateado como "DM" + SKU)
#    - titulo (título original obtenido de la web del producto)
#    - imagen (URL principal de la imagen del producto)
#    - imagenes (enlace de la imagen principal duplicado para compatibilidad)
#    - categoria_id / categoria_nombre (generados automáticamente mediante análisis 
#      del título: detecta conteo de piezas ej. "2000 piezas" u objetos "3D", 
#      omitiendo códigos numéricos del fabricante como 17128, 99004, etc.)
#    - subcategoria_id / subcategoria_nombre (replican la información y formato 
#      de la categoría principal)
#    - producto_descripcion (descripción extraída del detalle o título como respaldo)
#    - precio (precio sugerido ya calculado con costo adicional y margen de ganancia)
#    - estado (DISPONIBLE o AGOTADO según el botón de compra)
#    - precio_original (precio base de la tienda original)
#    - sku (código SKU original del producto)
#    - empresa (campo con valor fijo por defecto: "DEMUSEO")
# 2. Actualización de la GUI (Versión 1) con visualización en vivo de la extracción.
# ==============================================================================

import time, csv, threading, os, math, re
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def analizar_categoria(titulo):
    """
    Analiza el título para extraer la categoría y subcategoría.
    1. Revisa si contiene la palabra clave '3D'.
    2. Busca números correspondientes al conteo de piezas habituales (ej. 500, 1000, 2000, etc.),
       omitiendo códigos de producto numéricos.
    """
    titulo_upper = titulo.upper()
    
    # 1. Evaluar si es Rompecabezas 3D
    if re.search(r'\b3D\b', titulo_upper):
        cat_id = "rompecabezas_3d"
        cat_nombre = "Rompecabezas 3D"
        return cat_id, cat_nombre, cat_id, cat_nombre

    # 2. Cantidades de piezas estándar en rompecabezas para evitar confundir con códigos de producto
    piezas_comunes = {12, 24, 30, 35, 48, 50, 60, 100, 150, 200, 250, 300, 500, 1000, 1500, 2000, 3000, 4000, 5000, 6000, 9000, 13200, 18000, 32000, 40000}

    match_piezas = re.search(r'\b(\d{2,5})\s*(?:PIEZAS|PZS|PCS|PZB)?\b', titulo_upper)
    if match_piezas:
        num = int(match_piezas.group(1))
        if num in piezas_comunes or re.search(r'\b' + str(num) + r'\s*(?:PIEZAS|PZS|PCS)\b', titulo_upper):
            cat_id = f"{num}_piezas"
            cat_nombre = f"{num} piezas"
            return cat_id, cat_nombre, cat_id, cat_nombre

    numeros = re.findall(r'\b\d+\b', titulo_upper)
    for n in numeros:
        val = int(n)
        if val in piezas_comunes:
            cat_id = f"{val}_piezas"
            cat_nombre = f"{val} piezas"
            return cat_id, cat_nombre, cat_id, cat_nombre

    return "general", "General", "general", "General"


def iniciar_scraping(log_widget, var_titulo, var_contador, var_detalle,
                     entry_archivo, entry_recoleccion, entry_ganancia):
    
    ARCHIVO_SALIDA = entry_archivo.get()
    try:
        COSTO_ADICIONAL = float(entry_recoleccion.get())
        PORCENTAJE_GANANCIA = float(entry_ganancia.get()) / 100
    except ValueError:
        messagebox.showerror("Error", "Costo y Ganancia deben ser números.")
        return
    
    if not os.path.exists(os.path.dirname(ARCHIVO_SALIDA)): 
        os.makedirs(os.path.dirname(ARCHIVO_SALIDA))
    
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    driver = webdriver.Chrome(options=options)
    
    datos = []
    totales = {"disp": 0, "agot": 0}
    
    try:
        for i in range(1, 21):
            driver.get(f"https://demuseo.com/categoria-producto/juegos-mesa-y-rompecabezas/rompecabezas-juegos-mesa/page/{i}/")
            time.sleep(3)
            productos = driver.find_elements(By.CSS_SELECTOR, ".jet-listing-grid__item")
            if not productos: break
            
            for j in range(len(productos)):
                productos = driver.find_elements(By.CSS_SELECTOR, ".jet-listing-grid__item")
                p = productos[j]
                
                try:
                    btn = p.find_element(By.CSS_SELECTOR, ".jet-woo-builder-archive-add-to-cart a, .elementor-button")
                    estado = "DISPONIBLE" if "añadir" in btn.text.lower() else "AGOTADO"
                    
                    titulo = p.find_element(By.CSS_SELECTOR, ".product_title").text
                    precio_txt = p.find_element(By.CSS_SELECTOR, ".price").text
                    precio_orig = float(''.join(c for c in precio_txt if c.isdigit() or c == '.'))
                    
                    precio_sugerido = math.ceil(precio_orig + COSTO_ADICIONAL + (precio_orig * PORCENTAJE_GANANCIA))
                    
                    link = p.find_element(By.TAG_NAME, "a").get_attribute("href")
                    driver.execute_script("window.open('');")
                    driver.switch_to.window(driver.window_handles[1])
                    driver.get(link)
                    
                    img_real = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".wp-post-image, .woocommerce-product-gallery__image img"))
                    ).get_attribute("src")
                    
                    try:
                        desc_elem = driver.find_elements(By.CSS_SELECTOR, ".woocommerce-product-details__short-description, #tab-description")
                        producto_descripcion = desc_elem[0].text.strip() if desc_elem and desc_elem[0].text.strip() else titulo
                    except Exception:
                        producto_descripcion = titulo
                    
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                    
                    sku = btn.get_attribute("data-product_sku") or "N/A"
                    if estado == "DISPONIBLE": totales["disp"] += 1
                    else: totales["agot"] += 1
                    
                    cat_id, cat_nom, subcat_id, subcat_nom = analizar_categoria(titulo)
                    
                    id_propio = f"DM{sku}"
                    empresa = "DEMUSEO"
                    imagenes = img_real
                    
                    datos.append([
                        id_propio, titulo, img_real, imagenes,
                        cat_id, cat_nom, subcat_id, subcat_nom,
                        producto_descripcion, precio_sugerido, estado,
                        precio_orig, sku, empresa
                    ])
                    
                    # Reflejar datos extraídos en pantalla en tiempo real
                    var_titulo.set(f"Producto: {titulo}")
                    var_contador.set(f"Procesados: {len(datos)} (Disp: {totales['disp']} | Agot: {totales['agot']})")
                    var_detalle.set(f"SKU: {sku} | Cat: {cat_nom} | Precio Sug: {precio_sugerido}")
                    
                    log_widget.insert(tk.END, f"[OK] SKU: {sku} | {titulo} | Cat: {cat_nom} | Precio: {precio_sugerido}\n")
                    log_widget.see(tk.END)
                except Exception:
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                    continue
        
        encabezados = [
            "id", "titulo", "imagen", "imagenes", 
            "categoria_id", "categoria_nombre", "subcategoria_id", "subcategoria_nombre", 
            "producto_descripcion", "precio", "estado", "precio_original", "sku", "empresa"
        ]
        
        with open(ARCHIVO_SALIDA, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(encabezados)
            writer.writerows(datos)
            
        messagebox.showinfo("Finalizado", f"Resumen Versión 1:\n{totales['disp']} disponibles, {totales['agot']} agotados.")
    finally:
        driver.quit()

# --- GUI (Versión 1) ---
root = tk.Tk()
root.title("Scraper Demuseo - Versión 1")
root.geometry("700x680")

tk.Label(root, text="Ruta CSV de Salida:").pack(pady=2)
entry_ruta = tk.Entry(root, width=85)
entry_ruta.insert(0, r"D:\Projects\2026\Development\WebPages\Rompecabezas\Rompecabezas-v7\data\catalogo_rompecabezas.csv")
entry_ruta.pack(pady=2)

tk.Label(root, text="Costo Recolección:").pack(pady=2)
entry_reco = tk.Entry(root, width=15)
entry_reco.insert(0, "15.0")
entry_reco.pack(pady=2)

tk.Label(root, text="% Ganancia (ej 30):").pack(pady=2)
entry_gana = tk.Entry(root, width=15)
entry_gana.insert(0, "30")
entry_gana.pack(pady=2)

# Variables de estado visual en pantalla
var_titulo = tk.StringVar(value="Estado: En espera de inicio...")
var_contador = tk.StringVar(value="Procesados: 0")
var_detalle = tk.StringVar(value="Detalles de extracción en vivo aparecerán aquí...")

ttk.Label(root, textvariable=var_titulo, font=("Arial", 10, "bold"), foreground="navy").pack(pady=5)
ttk.Label(root, textvariable=var_contador, font=("Arial", 9)).pack(pady=2)
ttk.Label(root, textvariable=var_detalle, font=("Arial", 9, "italic"), foreground="darkgreen").pack(pady=2)

log_area = scrolledtext.ScrolledText(root, width=82, height=14)
log_area.pack(pady=10)

btn = tk.Button(root, text="INICIAR PROCESO (Versión 1)", bg="green", fg="white", font=("Arial", 10, "bold"),
                command=lambda: threading.Thread(target=iniciar_scraping, args=(
                    log_area, var_titulo, var_contador, var_detalle, 
                    entry_ruta, entry_reco, entry_gana
                )).start())
btn.pack(pady=10)

root.mainloop()