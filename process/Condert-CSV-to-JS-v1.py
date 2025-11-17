import csv
import json
import os
from datetime import datetime

# ----------------------------------------------------------------------
# CONFIGURACIÓN DE RUTAS
# ----------------------------------------------------------------------
csv_file = './data/rompecabezas-v2.csv'
js_file  = './js/productos.js'

# ----------------------------------------------------------------------
# VALIDAR ARCHIVO CSV
# ----------------------------------------------------------------------
if not os.path.exists(csv_file):
    raise FileNotFoundError(f"Archivo CSV no encontrado: {csv_file}")

productos = []

# ----------------------------------------------------------------------
# LEER CSV
# ----------------------------------------------------------------------
with open(csv_file, mode='r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)

    # Normalizar nombres de columnas
    reader.fieldnames = [name.strip().lower() for name in reader.fieldnames]

    # Columnas requeridas
    requeridos = [
        'id', 'titulo', 'imagen',
        'categoria_id', 'categoria_nombre',
        'subcategoria_id', 'subcategoria_nombre',
        'producto_descripcion', 'precio'
    ]

    faltantes = [c for c in requeridos if c not in reader.fieldnames]
    if faltantes:
        raise KeyError(f"Faltan columnas en el CSV: {faltantes}")

    # Procesar filas
    for row in reader:
        try:
            producto = {
                "id": row["id"].strip(),
                "titulo": row["titulo"].strip(),
                "imagen": row["imagen"].strip(),
                "categoria": {
                    "id": row["categoria_id"].strip(),
                    "nombre": row["categoria_nombre"].strip()
                },
                "subcategoria": {
                    "id": row["subcategoria_id"].strip(),
                    "nombre": row["subcategoria_nombre"].strip()
                },
                "descripcion": row["producto_descripcion"].strip(),
                "precio": float(row["precio"].strip())
            }
            productos.append(producto)
        except Exception as e:
            print(f"Error en fila: {row}")
            print(f"  -> {e}")

# ----------------------------------------------------------------------
# GENERAR ARCHIVO .JS CON: export const productos = [...]
# ----------------------------------------------------------------------
js_content = f"""// rompecabezas-v2.js
// Generado automáticamente el {datetime.now().strftime('%Y-%m-%d a las %H:%M')}
// Fuente: {os.path.basename(csv_file)}
// Total productos: {len(productos)}

export const productos = {json.dumps(productos, indent=4, ensure_ascii=False)};
"""

# Guardar archivo
with open(js_file, 'w', encoding='utf-8') as f:
    f.write(js_content)

print(f"Conversión exitosa!")
print(f"   Productos: {len(productos)}")
print(f"   Archivo: {js_file}")