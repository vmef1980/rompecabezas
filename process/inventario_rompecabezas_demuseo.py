import time, csv, threading, os, math
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def iniciar_scraping(log_widget, var_sku, var_titulo, var_estado, var_contador, 
                     entry_archivo, entry_recoleccion, entry_ganancia):
    
    # Obtener valores de la GUI
    ARCHIVO_SALIDA = entry_archivo.get()
    try:
        COSTO_ADICIONAL = float(entry_recoleccion.get())
        PORCENTAJE_GANANCIA = float(entry_ganancia.get()) / 100
    except ValueError:
        messagebox.showerror("Error", "Costo y Ganancia deben ser números.")
        return
    
    if not os.path.exists(os.path.dirname(ARCHIVO_SALIDA)): os.makedirs(os.path.dirname(ARCHIVO_SALIDA))
    
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
                # Recargamos la lista para evitar errores de elemento stale
                productos = driver.find_elements(By.CSS_SELECTOR, ".jet-listing-grid__item")
                p = productos[j]
                
                try:
                    btn = p.find_element(By.CSS_SELECTOR, ".jet-woo-builder-archive-add-to-cart a, .elementor-button")
                    estado = "DISPONIBLE" if "añadir" in btn.text.lower() else "AGOTADO"
                    
                    titulo = p.find_element(By.CSS_SELECTOR, ".product_title").text
                    precio_txt = p.find_element(By.CSS_SELECTOR, ".price").text
                    precio_orig = float(''.join(c for c in precio_txt if c.isdigit() or c == '.'))
                    
                    # Cálculo: ROUNDUP(Precio + 15 + (Precio * 0.3))
                    precio_sugerido = math.ceil(precio_orig + COSTO_ADICIONAL + (precio_orig * PORCENTAJE_GANANCIA))
                    
                    # Navegación al detalle para obtener imagen real
                    link = p.find_element(By.TAG_NAME, "a").get_attribute("href")
                    driver.execute_script("window.open('');")
                    driver.switch_to.window(driver.window_handles[1])
                    driver.get(link)
                    
                    # Extracción de imagen de alta calidad
                    img_real = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".wp-post-image, .woocommerce-product-gallery__image img"))
                    ).get_attribute("src")
                    
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                    
                    sku = btn.get_attribute("data-product_sku") or "N/A"
                    if estado == "DISPONIBLE": totales["disp"] += 1
                    else: totales["agot"] += 1
                    
                    datos.append([f"DM{sku}", sku, titulo, img_real, precio_orig, precio_sugerido, estado])
                    
                    var_titulo.set(f"Producto: {titulo}")
                    var_contador.set(f"Procesados: {len(datos)}")
                    log_widget.insert(tk.END, f"Procesado: {titulo}\n")
                    log_widget.see(tk.END)
                except Exception:
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                    continue
        
        with open(ARCHIVO_SALIDA, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["id_propio", "SKU", "Titulo", "Url", "Precio Original", "Precio Sugerido", "Estado"])
            writer.writerows(datos)
        messagebox.showinfo("Finalizado", f"Resumen: {totales['disp']} disp, {totales['agot']} agot.")
    finally:
        driver.quit()

# --- GUI ---
root = tk.Tk()
root.title("Scraper Profesional v5.0")
root.geometry("650x650")

tk.Label(root, text="Ruta CSV:").pack()
entry_ruta = tk.Entry(root, width=80); entry_ruta.insert(0, r"D:\Projects\2026\Development\WebPages\Rompecabezas\Rompecabezas-v7\data\catalogo_rompecabezas.csv"); entry_ruta.pack()
tk.Label(root, text="Costo Recolección:").pack(); entry_reco = tk.Entry(root, width=10); entry_reco.insert(0, "15.0"); entry_reco.pack()
tk.Label(root, text="% Ganancia (ej 30):").pack(); entry_gana = tk.Entry(root, width=10); entry_gana.insert(0, "30"); entry_gana.pack()

var_titulo, var_contador = tk.StringVar(), tk.StringVar(value="Procesados: 0")
ttk.Label(root, textvariable=var_titulo, font=("Arial", 10, "bold")).pack(pady=5)
ttk.Label(root, textvariable=var_contador).pack()

log_area = scrolledtext.ScrolledText(root, width=75, height=12); log_area.pack(pady=10)
btn = tk.Button(root, text="INICIAR PROCESO", bg="green", fg="white", command=lambda: threading.Thread(target=iniciar_scraping, args=(log_area, tk.StringVar(), var_titulo, tk.StringVar(), var_contador, entry_ruta, entry_reco, entry_gana)).start())
btn.pack(pady=10)
root.mainloop()