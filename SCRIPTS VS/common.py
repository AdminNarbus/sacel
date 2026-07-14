from pathlib import Path
import os
import time

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent


def repo_path(*parts):
    return ROOT_DIR.joinpath(*parts)


def script_path(name: str):
    return SCRIPTS_DIR / name


def ensure_dirs(*paths):
    for path in paths:
        Path(path).mkdir(parents=True, exist_ok=True)


def env_bool(nombre, default=False):
    valor = os.getenv(nombre)
    if valor is None:
        return default
    return valor.strip().lower() in ("true", "1", "yes", "y", "si")


def ejecutar_con_reintentos(funcion, nombre, max_intentos=3, espera=15):
    intento = 1
    while intento <= max_intentos:
        print("\n------------------------------------------------------------")
        print(f"[REINTENTO] {nombre} | Intento {intento} de {max_intentos}")
        print("------------------------------------------------------------")
        try:
            resultado = funcion()
            print(f"[OK] {nombre} finalizado correctamente")
            return resultado
        except Exception as e:
            print(f"[ERROR] {nombre} falló en intento {intento}")
            print(f"        Motivo: {e}")
            if intento == max_intentos:
                print(f"[FATAL] {nombre} falló definitivamente")
                raise
            print(f"[INFO] Esperando {espera} segundos antes de reintentar...\n")
            time.sleep(espera)
            intento += 1


def verificar_descarga(carpeta, tiempo_inicio, extensions=(".xls", ".xlsx"), timeout=180):
    carpeta = Path(carpeta)
    for _ in range(timeout):
        archivos = [f for f in carpeta.iterdir() if f.is_file()]
        nuevos = [f for f in archivos if f.stat().st_ctime >= (tiempo_inicio - 10)]

        if any(str(f).lower().endswith((".crdownload", ".tmp")) for f in nuevos):
            time.sleep(1)
            continue

        final = next((f for f in nuevos if f.suffix.lower() in extensions), None)
        if final and final.stat().st_size > 0:
            return final

        time.sleep(1)
    return None


def inyectar_fecha_js(driver, id_elemento, valor_fecha):
    script = f"""
    var elem = document.getElementById('{id_elemento}');
    if(elem) {{
        elem.value = '{valor_fecha}';
        elem.dispatchEvent(new Event('input', {{ bubbles: true }}));
        elem.dispatchEvent(new Event('change', {{ bubbles: true }}));
        elem.dispatchEvent(new Event('blur', {{ bubbles: true }}));
    }}
    """
    driver.execute_script(script)
    print(f"      [INFO] Fecha inyectada en {id_elemento}: {valor_fecha}")


def chrome_options_descargas(carpeta_descargas):
    """Chrome estable para robots Sacel.

    En CI se usa Chrome con pantalla virtual (xvfb), igual que el pipeline
    Scania. Localmente se mantiene headless por defecto para no abrir ventana.
    """
    from selenium import webdriver

    download_dir = str(Path(carpeta_descargas).resolve())
    headless = env_bool("SACEL_HEADLESS", default=not env_bool("CI", False))

    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.page_load_strategy = "eager"

    chrome_bin = find_chrome_binary()
    if chrome_bin:
        options.binary_location = chrome_bin

    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_settings.popups": 0,
    }
    options.add_experimental_option("prefs", prefs)
    return options


def preparar_chrome_descargas(driver, carpeta_descargas):
    download_dir = str(Path(carpeta_descargas).resolve())
    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": download_dir,
        })
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
    except Exception as exc:
        print(f"[WARN] No se pudo aplicar configuracion CDP de Chrome: {exc}")


def guardar_screenshot_error(driver, nombre):
    try:
        ruta = ROOT_DIR / nombre
        driver.save_screenshot(str(ruta))
        print(f"[DEBUG] Captura de error guardada en: {ruta}")
    except Exception as exc:
        print(f"[WARN] No se pudo guardar captura de error: {exc}")


def find_chrome_binary():
    """Return Chrome/Chromium binary path.

    Order:
    - `CHROME_BIN`, `CHROME_PATH` env vars
    - common install locations on Windows
    - None if not found
    """
    import os

    for env in ("CHROME_BIN", "CHROME_PATH", "GOOGLE_CHROME_SHIM"):
        val = os.environ.get(env)
        if val and Path(val).exists():
            return str(val)

    possible = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Chromium\Application\chrome.exe",
        r"C:\Program Files (x86)\Chromium\Application\chrome.exe",
    ]
    for p in possible:
        if Path(p).exists():
            return str(p)

    return None


def db_config():
    """Return psycopg2 connection kwargs from .env.

    Supports either split DB_* variables or a single DEV_DATABASE_URL/DATABASE_URL.
    """
    import os
    from dotenv import load_dotenv

    load_dotenv(ROOT_DIR / ".env")

    host = os.getenv("DB_HOST")
    database = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    sslmode = os.getenv("DB_SSLMODE", "require")

    if all([host, database, user, password]):
        return dict(
            host=host,
            database=database,
            user=user,
            password=password,
            sslmode=sslmode,
        )

    database_url = os.getenv("DEV_DATABASE_URL") or os.getenv("DATABASE_URL")
    if database_url:
        return dict(dsn=database_url, sslmode=sslmode)

    raise RuntimeError(
        "Falta configurar la BD en .env: usa DB_HOST/DB_NAME/DB_USER/DB_PASSWORD "
        "o DEV_DATABASE_URL"
    )


def obtener_fechas_faltantes(tipo_robot, dias_atras=7):
    """Retorna la lista de objetos date (de los ultimos X dias) que no estan cargados en la BD."""
    import psycopg2
    import re
    from datetime import datetime, timedelta

    try:
        conn = psycopg2.connect(**db_config())
        cursor = conn.cursor()
        cursor.execute("SET search_path TO ranking_conductores;")
        
        hoy = datetime.now().date()
        fechas_rango = [hoy - timedelta(days=i) for i in range(1, dias_atras + 1)]
        
        if tipo_robot == "scania":
            cursor.execute("SELECT DISTINCT source_name FROM scania;")
            cargadas = set()
            for r in cursor.fetchall():
                m = re.search(r"Reporte_Scania_(\d{4}-\d{2}-\d{2})", r[0])
                if m:
                    cargadas.add(datetime.strptime(m.group(1), "%Y-%m-%d").date())
        elif tipo_robot == "excesos":
            cursor.execute("SELECT DISTINCT source_name FROM excesos_velocidad;")
            cargadas = set()
            for r in cursor.fetchall():
                m = re.search(r"Reporte_Excesos_Velocidad_(\d{2}-\d{2}-\d{4})", r[0])
                if m:
                    cargadas.add(datetime.strptime(m.group(1), "%d-%m-%Y").date())
        else:
            return [hoy - timedelta(days=1)]
            
        faltantes = [d for d in fechas_rango if d not in cargadas]
        
        cursor.close()
        conn.close()
        
        if not faltantes:
            print(f"[INFO] {tipo_robot.upper()} al dia. No hay fechas faltantes en los ultimos {dias_atras} dias.")
        else:
            print(f"[INFO] {tipo_robot.upper()} faltantes detectados: {[f.strftime('%Y-%m-%d') for f in sorted(faltantes)]}")
            
        return sorted(faltantes)
    except Exception as e:
        print(f"[WARN] Error al consultar BD para obtener fechas faltantes de {tipo_robot}: {e}")
        return [datetime.now().date() - timedelta(days=1)]

