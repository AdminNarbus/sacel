import time
import os
import shutil
import glob
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

from common import (
    repo_path,
    ejecutar_con_reintentos,
    inyectar_fecha_js,
    verificar_descarga,
    obtener_fechas_faltantes,
    chrome_options_descargas,
    preparar_chrome_descargas,
    guardar_screenshot_error,
)

# ==========================================
# CONFIGURACIÓN
# ==========================================
LISTA_EVENTOS_A_DESMARCAR = ["37"]

# ==========================================
# RUTAS DINÁMICAS (ArchivosBD)
# ==========================================
BASE = repo_path()
load_dotenv(BASE / ".env")
CARPETA_FINAL = BASE / "ExcesoVelocidadCSV"
CARPETA_DESCARGAS = str(CARPETA_FINAL)

def env_required(nombre):
    valor = os.getenv(nombre)
    if not valor:
        raise RuntimeError(f"Falta configurar {nombre} en el archivo .env o Secrets")
    return valor


USUARIO_SACEL = env_required("SACEL_USER")
CLAVE_SACEL = env_required("SACEL_PASSWORD")

# ==========================================
# FUNCIONES DEL ROBOT
# ==========================================
def click_rapido(driver, wait, by, selector):
    try:
        elem = wait.until(EC.element_to_be_clickable((by, selector)))
        elem.click()
    except:
        try:
            driver.execute_script(


                "arguments[0].click();",
                driver.find_element(by, selector)
            )
        except:
            pass

def deseleccionar_checkbox_especial(driver, valor_input):
    try:
        input_elem = driver.find_element(By.CSS_SELECTOR, f"input[value='{valor_input}']")
        padre_div = input_elem.find_element(By.XPATH, "./..")
        if "checked" in padre_div.get_attribute("class"):
            driver.execute_script(
                "arguments[0].click();",
                padre_div.find_element(By.TAG_NAME, "ins")
            )
    except:
        pass

def monitorear_tabla_y_descargar(driver):
    print("      [INFO] Monitoreando tabla (modo furtivo)")
    time.sleep(3)
    max_seg = 900
    inicio = time.time()

    while (time.time() - inicio) < max_seg:
        try:
            body = driver.find_element(By.TAG_NAME, "body").text
            if "Procesando" in body or "Cargando" in body:
                time.sleep(1)
                continue

            filas = driver.find_elements(By.CSS_SELECTOR, "tbody tr")
            if len(filas) > 0:
                if "Ningún dato" in filas[0].text:
                    if int(time.time()) % 10 == 0:
                        print(".", end="", flush=True)
                    time.sleep(1)
                    continue

                print(f"\n      [OK] Datos detectados ({len(filas)} filas). Exportando Excel")
                driver.execute_script(
                    "arguments[0].click();",
                    driver.find_element(By.CSS_SELECTOR, ".buttons-excel")
                )
                return True

            time.sleep(1)
        except:
            time.sleep(1)

    return False

# ==========================================
# ROBOT PRINCIPAL
# ==========================================
def iniciar_descarga_excesos(fechas=None):
    if not fechas:
        # Por defecto, ayer
        fechas = [datetime.now().date() - timedelta(days=1)]

    print("\n============================================================")
    print("[ROBOT SACEL] EXCESO DE VELOCIDAD")
    print(f"[ROBOT SACEL] Fechas a descargar: {[f.strftime('%Y-%m-%d') for f in fechas]}")
    print("============================================================")

    os.makedirs(CARPETA_DESCARGAS, exist_ok=True)

    options = chrome_options_descargas(CARPETA_DESCARGAS)
    driver = webdriver.Chrome(options=options)
    preparar_chrome_descargas(driver, CARPETA_DESCARGAS)
    driver.set_page_load_timeout(60)
    wait = WebDriverWait(driver, 20)

    try:
        print("[STEP 1] Iniciando sesión")
        driver.get("https://libreta.sacel.cl/articulo-25")
        wait.until(EC.visibility_of_element_located((By.NAME, "username"))).send_keys(USUARIO_SACEL)
        driver.find_element(By.NAME, "password").send_keys(CLAVE_SACEL + Keys.ENTER)

        wait.until(EC.element_to_be_clickable((By.ID, "btn_emp_1"))).click()
        try:
            wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "a[href='excesos-velocidad']")
                )
            ).click()
        except:
            driver.get("https://libreta.sacel.cl/excesos-velocidad")

        # Iterar sobre las fechas objetivo en la misma sesión
        for target_date in fechas:
            print(f"\n[FECHA] Procesando fecha: {target_date.strftime('%Y-%m-%d')}")
            fecha_str = target_date.strftime("%d-%m-%Y")

            ini = target_date.strftime("%d/%m/%Y 00:00")
            fin = target_date.strftime("%d/%m/%Y 23:59")

            print(f"[STEP] Configurando reporte para {fecha_str}")
            inyectar_fecha_js(driver, "fecha_desde", ini)
            inyectar_fecha_js(driver, "fecha_hasta", fin)

            try:
                driver.find_element(By.ID, "select2-velocidad-container").click()
                wait.until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, ".select2-search__field"))
                ).send_keys("101" + Keys.ENTER)
            except Exception as e:
                print(f"      [WARN] No se pudo configurar select2 limite velocidad: {e}")

            for v in LISTA_EVENTOS_A_DESMARCAR:
                deseleccionar_checkbox_especial(driver, v)

            click_rapido(driver, wait, By.ID, "btn_consultar")

            ts = time.time()
            if monitorear_tabla_y_descargar(driver):
                archivo = verificar_descarga(CARPETA_DESCARGAS, ts, timeout=120)
                if archivo:
                    os.makedirs(CARPETA_FINAL, exist_ok=True)
                    nombre_base = f"Reporte_Excesos_Velocidad_{fecha_str}"
                    nombre_xlsx = nombre_base + ".xlsx"
                    destino_xlsx = os.path.join(CARPETA_FINAL, nombre_xlsx)

                    try:
                        if os.path.exists(destino_xlsx):
                            os.remove(destino_xlsx)

                        shutil.move(archivo, destino_xlsx)
                        print("      [FILES] Excel descargado temporalmente")

                        ruta_csv_final = convertir_xlsx_a_csv_reparado(destino_xlsx)

                        if ruta_csv_final and os.path.exists(ruta_csv_final):
                            os.remove(destino_xlsx)
                            print("      [FILES] Excel eliminado (limpieza completada)")
                            print(f"      [FINAL] Archivo final: {os.path.basename(ruta_csv_final)}")
                        else:
                            print("      [WARN] No se borró el Excel porque falló la creación del CSV")
                    except Exception as e:
                        print(f"      [FILES ERROR] {e}")
                else:
                    print("      [ERROR] No se encontró el archivo descargado")
            else:
                print("      [INFO] No se detectaron excesos de velocidad para descargar en esta fecha.")

    except Exception as e:
        guardar_screenshot_error(driver, "error_sacel_excesos.png")
        print(f"[ERROR CRITICO] {e}")
        raise
    finally:
        driver.quit()

def ejecutar_descargas_completas():
    # Consultar BD por fechas faltantes en los últimos 7 días
    fechas = obtener_fechas_faltantes("excesos", dias_atras=7)
    if not fechas:
        print("[ROBOT EXCESO VELOCIDAD] Todo al día. No hay descargas pendientes.")
        return
    iniciar_descarga_excesos(fechas)

# ==========================================
# CONVERSIÓN A CSV (LIMPIO)
# ==========================================
def convertir_xlsx_a_csv_reparado(ruta_xlsx):
    print("[CSV] Generando archivo CSV limpio")
    try:
        ruta_csv = os.path.splitext(ruta_xlsx)[0] + ".csv"

        try:
            df = pd.read_excel(ruta_xlsx, engine='calamine', header=None)
        except:
            df = pd.read_excel(ruta_xlsx, header=None)

        start_idx = -1
        for i, row in df.head(20).iterrows():
            txt = row.astype(str).str.lower().tolist()
            if any('patente' in t for t in txt) or any('n° flota' in t for t in txt):
                start_idx = i
                break

        if start_idx == -1:
            start_idx = 0

        df_data = df.iloc[start_idx:].copy()
        df_data.columns = df_data.iloc[0]
        df_data = df_data[1:]

        cols_a_borrar = [c for c in df_data.columns if "localizac" in str(c).lower()]
        if cols_a_borrar:
            print(f"[CSV] Eliminando columna conflictiva: {cols_a_borrar}")
            df_data = df_data.drop(columns=cols_a_borrar)

        df_data.to_csv(
            ruta_csv,
            index=False,
            sep=',',
            encoding='utf-8-sig'
        )

        print(f"[CSV] OK: {os.path.basename(ruta_csv)}")
        return ruta_csv

    except Exception as e:
        print(f"[CSV ERROR] {e}")
        return None

# ==========================================
# MAIN
# ==========================================
if __name__ == "__main__":
    ejecutar_con_reintentos(
        ejecutar_descargas_completas,
        nombre="ROBOT EXCESO VELOCIDAD",
        max_intentos=3,
        espera=15
    )
