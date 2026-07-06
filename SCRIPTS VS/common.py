from pathlib import Path
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

