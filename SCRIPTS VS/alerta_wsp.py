import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import unicodedata
import sys
import os

# Forzar UTF-8 en stdout para soportar emojis en Windows
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from common import repo_path, db_config

print("\U0001f6a8 Script Alerta Diaria - SACEL + SCANIA (CON WhatsApp)")

# ==================================================
# CONFIGURACIÓN GENERAL
# ==================================================
BASE = repo_path()
load_dotenv(BASE / ".env")

SACEL_CSV = BASE / "SacelCSV"
SCANIA_CSV = BASE / "ScaniaCSV"

UMBRAL_HORAS_SACEL = 5.01
UMBRAL_RALENTI_SACEL = 10.0
UMBRAL_RALENTI_SCANIA = 18.0

PRECIO_DIESEL = 960
MAX_CHARS = 1550

# ==================================================
# CONFIGURACIÓN BD
# ==================================================
# ==================================================
# CONFIGURACIÓN TWILIO
# ==================================================
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM = os.getenv("TWILIO_FROM")
TWILIO_TO = [telefono.strip() for telefono in os.getenv("TWILIO_TO", "").split(",") if telefono.strip()]

# Permitir ejecutar en modo 'dry-run' para evitar envíos reales (usar SEND_WHATSAPP=false)
SEND_WHATSAPP = os.getenv("SEND_WHATSAPP", "true").strip().lower()
SEND_WHATSAPP_ENABLED = SEND_WHATSAPP not in ("false", "0", "no")

# ==================================================
# VALIDACION MODO
# ==================================================
def obtener_modo():
    if len(sys.argv) < 2:
        print("Uso: python alerta_wsp.py [sacel|scania]")
        sys.exit(1)

    modo = sys.argv[1].strip().lower()
    if modo not in ("sacel", "scania"):
        print("Modo inválido. Usa: sacel o scania")
        sys.exit(1)

    return modo

MODO = obtener_modo()

if MODO == "sacel":
    CONTROL_DIR = BASE / "logswsp"
    CONTROL_FILE = CONTROL_DIR / "last_alert_sent_sacel.txt"
else:
    CONTROL_DIR = BASE / "logswsp_scania"
    CONTROL_FILE = CONTROL_DIR / "last_alert_sent_scania.txt"

CONTROL_DIR.mkdir(exist_ok=True)

# ==================================================
# CONTROL DIARIO
# ==================================================
def ya_se_ejecuto_hoy():
    if not CONTROL_FILE.exists():
        return False
    return CONTROL_FILE.read_text().strip() == datetime.now().strftime("%Y-%m-%d")

def marcar_ejecucion_hoy():
    CONTROL_FILE.write_text(datetime.now().strftime("%Y-%m-%d"))

# ==================================================
# HELPERS GENERALES
# ==================================================
def agregar_si_cabe(bloque, lista_mensaje):
    mensaje_actual = "\n".join(lista_mensaje)
    if len(mensaje_actual) + len(bloque) + 1 <= MAX_CHARS:
        lista_mensaje.append(bloque)
        return True
    return False

def es_conduccion(valor):
    if pd.isna(valor):
        return False
    texto = str(valor).strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("ascii")
    return "conduc" in texto

def horas_entre(inicio, fin):
    return (fin - inicio).total_seconds() / 3600

def horas_a_hhmm(horas):
    h = int(horas)
    m = int(round((horas - h) * 60))
    if m == 60:
        h += 1
        m = 0
    return f"{h}h {m}m"

def parse_horas_minutos(valor):
    if pd.isna(valor):
        return None
    try:
        h, m = str(valor).split(":")
        return int(h) + int(m) / 60
    except:
        return None

def filas_datos_sacel(df_raw):
    for idx, row in df_raw.iterrows():
        valores = [str(v).strip().lower() for v in row.tolist()]
        if "tipo marcación" in valores or "tipo marcacion" in valores:
            return df_raw.iloc[idx + 1:].reset_index(drop=True)
    return df_raw.iloc[7:].reset_index(drop=True)

def to_numeric(valor):
    if pd.isna(valor):
        return None
    try:
        return float(str(valor).replace(",", "."))
    except:
        return None

def to_interval(valor):
    if pd.isna(valor):
        return None
    if isinstance(valor, str) and ":" in valor:
        try:
            h, m = valor.split(":")
            return f"{int(h)} hours {int(m)} minutes"
        except:
            return None
    return None

def subir_scania_bd(df_raw, source_name):
    import psycopg2

    print("Subiendo datos SCANIA a la base de datos (public.scania)...")
    df = df_raw.iloc[6:].copy()
    try:
        conn = psycopg2.connect(**db_config())
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1 FROM public.scania WHERE source_name=%s LIMIT 1;", (source_name,))
        if cursor.fetchone():
            print(f"[BD] OMITIDO (ya cargado): {source_name}")
            cursor.close()
            conn.close()
            return
            
        for _, row in df.iterrows():
            cursor.execute("""
                INSERT INTO public.scania (
                    vehiculo, consumo_medio_km_l, distancia_km, tiempo_motor,
                    aplic_freno_100, aplic_fuertes_freno_100, acel_fuerte_100,
                    ralenti_pct, exceso_velocidad_pct, inercia_pct,
                    driver_support_pct, pendientes_pct, anticipacion_pct,
                    uso_frenos_pct, seleccion_marcha_pct,
                    consumo_diesel_total_litros, consumo_diesel_ralenti_litros,
                    tiempo_motor_ralenti, distancia_crucero_km,
                    aplic_freno_cantidad, aplic_fuertes_freno_cantidad,
                    fecha_reporte, source_name
                )
                VALUES (
                    %s,%s,%s,%s::interval,
                    %s,%s,%s,
                    %s,%s,%s,
                    %s,%s,%s,
                    %s,%s,
                    %s,%s,
                    %s::interval,%s,
                    %s,%s,
                    %s,%s
                );
            """, (
                row[1],
                to_numeric(row[2]),
                to_numeric(row[6]),
                to_interval(row[7]),
                to_numeric(row[11]),
                to_numeric(row[12]),
                to_numeric(row[13]),
                to_numeric(row[14]),
                to_numeric(row[16]),
                to_numeric(row[18]),
                to_numeric(row[19]),
                to_numeric(row[20]),
                to_numeric(row[21]),
                to_numeric(row[22]),
                None, # seleccion_marcha_pct
                to_numeric(row[23]),
                to_numeric(row[24]),
                to_interval(row[35]),
                to_numeric(row[38]),
                to_numeric(row[43]),
                to_numeric(row[44]),
                fecha_str,
                source_name
            ))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"[BD] OK: {source_name} cargado en public.scania.")
    except Exception as e:
        print(f"[BD] Error al subir a la BD: {e}")

# ==================================================
# CONTROL INICIAL
# ==================================================

# ==================================================
# FECHA AYER
# ==================================================
fecha_ayer = datetime.now() - timedelta(days=1)
fecha_str = fecha_ayer.strftime("%Y-%m-%d")
fecha_reporte = fecha_ayer.strftime("%d/%m/%Y")

# ==================================================
# SACEL
# ==================================================
def construir_alerta_sacel():
    sacel_alertas = []

    for archivo in sorted(SACEL_CSV.glob("*.csv")):
        df_raw = pd.read_csv(archivo, encoding="latin1", sep=",", header=None)
        df = filas_datos_sacel(df_raw)

        for _, row in df.iterrows():
            if pd.isna(row[6]) or pd.isna(row[7]) or pd.isna(row[9]):
                continue

            if not es_conduccion(row[2]):
                continue

            inicio = pd.to_datetime(row[6], dayfirst=True, errors="coerce")
            fin = pd.to_datetime(row[7], dayfirst=True, errors="coerce")

            if pd.isna(inicio) or pd.isna(fin):
                continue

            if inicio.date() != fecha_ayer.date():
                continue

            horas = horas_entre(inicio, fin)
            if horas <= UMBRAL_HORAS_SACEL:
                continue

            try:
                bus = int(float(row[9]))
            except:
                bus = row[9]

            sacel_alertas.append(
                f"• {row[4]}\n"
                f"   Bus {bus}\n"
                f"   {inicio.strftime('%d/%m %H:%M')} → {fin.strftime('%d/%m %H:%M')}\n"
                f"   Total: {horas_a_hhmm(horas)}\n"
            )

    mensaje = [
        f"🚨 ALERTA DIARIA – {fecha_reporte}",
        ""
    ]

    if sacel_alertas:
        agregar_si_cabe("⏱️ SACEL – Conducciones > 5 horas\n", mensaje)
        for alerta in sacel_alertas:
            if not agregar_si_cabe(alerta, mensaje):
                break

    return "\n".join(mensaje)

# ==================================================
# SCANIA
# ==================================================
def construir_alerta_scania():
    scania_alertas = []
    litros_ralenti_total = 0.0
    dinero_ralenti_total = 0.0

    archivo_scania = next(
        (a for a in SCANIA_CSV.glob("*.csv") if fecha_str in a.name),
        None
    )

    if archivo_scania:
        df_raw = pd.read_csv(archivo_scania, encoding="utf-8", sep=";", header=None)
        
        # Cargar a la base de datos
        subir_scania_bd(df_raw, archivo_scania.name)
        
        df = df_raw.iloc[6:].reset_index(drop=True)

        df = df[df[1].astype(str).str.lower() != "todos"]

        df["vehiculo"] = df[1]
        df["km_total"] = pd.to_numeric(df[6].astype(str).str.replace(",", "."), errors="coerce")
        df["tiempo_motor"] = df[7].apply(parse_horas_minutos)
        df["ralenti_pct"] = pd.to_numeric(df[14].astype(str).str.replace(",", "."), errors="coerce")
        df["ralenti_litros"] = pd.to_numeric(df[25].astype(str).str.replace(",", "."), errors="coerce")

        litros_ralenti_total = df["ralenti_litros"].sum(skipna=True)
        dinero_ralenti_total = litros_ralenti_total * PRECIO_DIESEL

        for _, r in df[df["ralenti_pct"] > UMBRAL_RALENTI_SCANIA].iterrows():
            tiempo_motor = r["tiempo_motor"]
            ralenti_pct = r["ralenti_pct"]

            if pd.isna(tiempo_motor) or pd.isna(ralenti_pct):
                continue

            tiempo = tiempo_motor * (ralenti_pct / 100)
            km = int(r["km_total"]) if pd.notna(r["km_total"]) else 0

            scania_alertas.append(
                f"• Vehículo {r['vehiculo']}\n"
                f"   Ralentí: {r['ralenti_pct']:.1f}% | KM: {km:,}".replace(",", ".") + "\n"
                f"   Tiempo ralentí: {horas_a_hhmm(tiempo)}\n"
            )

    scania_alertas.sort(
        key=lambda x: float(x.split("Ralentí:")[1].split("%")[0]),
        reverse=True
    )

    mensaje = [
        f"🚨 ALERTA DIARIA – {fecha_reporte}",
        ""
    ]

    if scania_alertas:
        agregar_si_cabe("🚗 SCANIA – Mayor ralentí\n", mensaje)
        for alerta in scania_alertas:
            if not agregar_si_cabe(alerta, mensaje):
                break

    if litros_ralenti_total > 0:
        resumen = (
            "\n⛽ RESUMEN RALENTÍ\n"
            f"   Litros: {litros_ralenti_total:,.0f}\n"
            f"   Costo: ${dinero_ralenti_total:,.0f}"
        ).replace(",", ".")
        agregar_si_cabe(resumen, mensaje)

    return "\n".join(mensaje)

# ==================================================
# MENSAJE FINAL
# ==================================================
if MODO == "sacel":
    mensaje_final = construir_alerta_sacel()
else:
    mensaje_final = construir_alerta_scania()

if len(mensaje_final.strip()) < 20:
    marcar_ejecucion_hoy()
    print(f"ℹ️ No hay contenido para enviar en {MODO}.")
    sys.exit(0)

print("\n📨 MENSAJE FINAL\n" + "=" * 80)
print(mensaje_final)
print("=" * 80)

# ==================================================
# ENVÍO WHATSAPP (o simulación si SEND_WHATSAPP está desactivado)
# ==================================================
if SEND_WHATSAPP_ENABLED:
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_FROM or not TWILIO_TO:
        raise RuntimeError("Faltan variables TWILIO_* en el archivo .env")

    from twilio.rest import Client

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    for telefono in TWILIO_TO:
        try:
            client.messages.create(
                from_=TWILIO_FROM,
                to=telefono,
                body=mensaje_final
            )
            print(f"mensaje enviado a {telefono}")
        except Exception as e:
            print(f"Error al enviar a {telefono}:{e}")
    marcar_ejecucion_hoy()
    print(f"✅ WhatsApp {MODO} enviado correctamente")
else:
    print("[DRY-RUN] SEND_WHATSAPP está desactivado. No se enviarán mensajes WhatsApp.")
    for telefono in TWILIO_TO:
        print(f"[DRY-RUN] simulando envío a {telefono}")
    marcar_ejecucion_hoy()
    print(f"✅ Dry-run completado para {MODO} (mensajes no enviados)")
