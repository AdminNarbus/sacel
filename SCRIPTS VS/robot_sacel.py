import time
import os
import shutil
import glob
import locale
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

from dotenv import load_dotenv
from common import repo_path, inyectar_fecha_js, verificar_descarga, find_chrome_binary

# ==========================================
# CONFIGURACIÓN Y RUTAS DINÁMICAS
# =========================================

BASE = repo_path()
load_dotenv(BASE / ".env")
CARPETA_FINAL = BASE / "SacelExcel"
CARPETA_DESCARGAS = str(CARPETA_FINAL)

def env_required(nombre):
    valor = os.getenv(nombre)
    if not valor:
        raise RuntimeError(f"Falta configurar {nombre} en el archivo .env o Secrets")
    return valor


USUARIO_SACEL = env_required("SACEL_USER")
CLAVE_SACEL = env_required("SACEL_PASSWORD")

try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except:
    pass

# ==========================================
# FUNCIONES AUXILIARES
# ==========================================

def esperar_tabla_cargada(driver):
    print("      [INFO] Ejecutando consulta y esperando datos...")

    try:
        btn = driver.find_element(By.ID, "btn_consultar")
        driver.execute_script("arguments[0].click();", btn)
    except:
        try:
            driver.find_element(By.XPATH, "//button[contains(., 'Consultar')]").click()
        except:
            pass

    tiempo_maximo = 1200  # 20 minutos
    inicio = time.time()

    while (time.time() - inicio) < tiempo_maximo:
        try:
            filas = driver.find_elements(By.CSS_SELECTOR, "#tabla tbody tr")
            texto_tabla = driver.find_element(By.ID, "tabla").text

            if len(filas) > 0 and "Ningún dato" not in texto_tabla:
                print(f"      [OK] Datos cargados ({len(filas)} filas)")
                return True

            time.sleep(2)

        except:
            time.sleep(2)

    # ⛔ CLAVE: timeout cuenta como fallo → reintento
    print("      [ERROR] Timeout esperando datos en la tabla")
    raise TimeoutException("Timeout esperando datos en la tabla SACEL")



# ==========================================
# ROBOT PRINCIPAL
# ==========================================

def iniciar_robot_sacel_mensual():
    print("\n============================================================")
    print("[ROBOT SACEL] ACTIVIDADES POR FECHA - MENSUAL")
    print(f"[ROBOT SACEL] Carpeta destino: {CARPETA_FINAL}")
    print("============================================================")

    os.makedirs(CARPETA_FINAL, exist_ok=True)

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    chrome_bin = find_chrome_binary()
    if chrome_bin:
        options.binary_location = chrome_bin

    prefs = {
        "download.default_directory": CARPETA_DESCARGAS,
        "download.prompt_for_download": False
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 30)

    archivo_descargado = None

    try:
        print("[STEP 1] Accediendo a Sacel")
        driver.get("https://libreta.sacel.cl/articulo-25")

        wait.until(
            EC.visibility_of_element_located((By.NAME, "username"))
        ).send_keys(USUARIO_SACEL)

        driver.find_element(By.NAME, "password").send_keys(CLAVE_SACEL)

        try:
            driver.find_element(By.NAME, "submit").click()
        except:
            driver.execute_script(
                "arguments[0].click();",
                driver.find_element(By.NAME, "submit")
            )

        print("[STEP 2] Navegando a reporte de actividades")
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "btn_emp_1"))).click()
            wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Actividades por Fecha"))).click()
        except:
            driver.get("https://libreta.sacel.cl/reporte-actividades")

        ahora = datetime.now()
        ini_str = ahora.replace(day=1, hour=0, minute=0).strftime("%d/%m/%Y %H:%M")
        fin_str = ahora.strftime("%d/%m/%Y %H:%M")

        print(f"[STEP 3] Aplicando filtros: {ini_str} -> {fin_str}")
        inyectar_fecha_js(driver, "fecha_desde", ini_str)
        inyectar_fecha_js(driver, "fecha_hasta", fin_str)

        if esperar_tabla_cargada(driver):
            print("[STEP 4] Descargando Excel")
            ts = time.time()

            try:
                btn = driver.find_element(By.CSS_SELECTOR, ".buttons-excel")
                driver.execute_script("arguments[0].click();", btn)
            except:
                try:
                    driver.find_element(
                        By.XPATH, "//button[contains(text(), 'Excel')]"
                    ).click()
                except:
                    pass

            archivo_descargado = verificar_descarga(CARPETA_DESCARGAS, ts)

    finally:
        try:
            driver.quit()
        except:
            pass
        print("[ROBOT SACEL] Navegador cerrado")

    return archivo_descargado

# ==========================================
# GESTIÓN DE ARCHIVOS
# ==========================================

def mover_archivo_mes(archivo_origen):
    if not archivo_origen:
        return

    print("[FILES] Procesando archivo mensual")

    nombres_meses = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
        5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
        9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
    }

    fecha_hoy = datetime.now()
    nombre_archivo = f"{nombres_meses[fecha_hoy.month]}_{fecha_hoy.year}.xls"
    ruta_destino = os.path.join(CARPETA_FINAL, nombre_archivo)

    if os.path.exists(ruta_destino):
        os.remove(ruta_destino)
        print(f"[FILES] Reemplazando archivo existente: {nombre_archivo}")

    shutil.move(archivo_origen, ruta_destino)
    print(f"[FILES] Archivo guardado como: {nombre_archivo}")

# ==========================================
# LÓGICA DE REINTENTOS
# ==========================================

def ejecutar_con_reintentos(funcion, nombre, max_intentos=3, espera=15):
    intento = 1

    while intento <= max_intentos:
        print("\n------------------------------------------------------------")
        print(f"[REINTENTO] {nombre} | Intento {intento} de {max_intentos}")
        print("------------------------------------------------------------")

        try:
            archivo = funcion()
            if archivo:
                mover_archivo_mes(archivo)

            print(f"[OK] {nombre} finalizado correctamente")
            return True

        except Exception as e:
            print(f"[ERROR] {nombre} falló en intento {intento}")
            print(f"        Motivo: {e}")

            if intento == max_intentos:
                print(f"[FATAL] {nombre} falló definitivamente")
                return False

            print(f"[INFO] Esperando {espera} segundos antes de reintentar...\n")
            time.sleep(espera)
            intento += 1

# ==========================================
# EJECUCIÓN
# ==========================================

if __name__ == "__main__":
    ejecutar_con_reintentos(
        iniciar_robot_sacel_mensual,
        nombre="ROBOT SACEL",
        max_intentos=1,
        espera=15
    )
