print("\n============================================================")
print("SCRIPT SUBIR CSV A BASE DE DATOS")
print("============================================================\n")

import psycopg2
import pandas as pd
from psycopg2.extras import execute_batch
from pathlib import Path
import unicodedata
import re
import os
import argparse

from dotenv import load_dotenv
from common import repo_path, db_config

# ======================
# CONFIGURACIÓN GENERAL
# ======================
BASE = repo_path()
load_dotenv(BASE / ".env")

SACEL_CSV   = BASE / "SacelCSV"
SCANIA_CSV  = BASE / "ScaniaCSV"
EXCESO_CSV  = BASE / "ExcesoVelocidadCSV"

DB_CONFIG = db_config()

SCHEMA = "ranking_conductores"

# ======================
# CONEXIÓN BD
# ======================
def conectar_bd():
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute(f"SET search_path TO {SCHEMA};")
    return conn, cursor

# ======================
# HELPERS COMUNES
# ======================
def limpiar_rut(rut):
    if rut is None:
        return None
    rut = str(rut).strip()
    if rut.lower() in ["", "nan", "0-0", "none"]:
        return None
    return rut.replace(".", "")

def to_numeric(valor):
    if pd.isna(valor):
        return None
    try:
        return float(str(valor).replace(",", "."))
    except:
        return None

def to_int(valor):
    try:
        return int(float(valor))
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

# ======================
# NORMALIZACIÓN EXCESOS
# ======================
def normalizar_columnas(df):
    cols = []
    for c in df.columns:
        c = unicodedata.normalize("NFKD", str(c))
        c = c.encode("ascii", "ignore").decode("ascii")
        c = c.lower().replace("/", "_")
        c = re.sub(r"[^a-z0-9_]", "_", c)
        c = re.sub(r"_+", "_", c).strip("_")
        cols.append(c)
    df.columns = cols
    return df


def filas_datos_sacel(df_raw):
    for idx, row in df_raw.iterrows():
        valores = [str(v).strip().lower() for v in row.tolist()]
        if "tipo marcación" in valores or "tipo marcacion" in valores:
            return df_raw.iloc[idx + 1:].copy().reset_index(drop=True)
    return df_raw.iloc[7:].copy().reset_index(drop=True)

# ======================
# CARGA SACEL
# ======================
def cargar_sacel(cursor, conn):
    print("\n------------------------------------------------------------")
    print("[SACEL] INICIO CARGA DE DATOS")
    print("------------------------------------------------------------")

    total_procesadas = 0
    total_saltadas = 0

    for archivo in sorted(SACEL_CSV.glob("*.csv")):
        print(f"[SACEL] Procesando archivo: {archivo.name}")

        df_raw = pd.read_csv(archivo, encoding="latin1", sep=",", header=None)
        df = filas_datos_sacel(df_raw)

        registros = []
        saltadas = 0

        for _, row in df.iterrows():
            if pd.isna(row[2]) or pd.isna(row[6]) or pd.isna(row[9]):
                saltadas += 1
                continue

            rut = limpiar_rut(row[3])
            if rut is None:
                saltadas += 1
                continue

            inicio = pd.to_datetime(row[6], dayfirst=True, errors="coerce")
            fin    = pd.to_datetime(row[7], dayfirst=True, errors="coerce")

            if pd.isna(inicio):
                saltadas += 1
                continue

            registros.append((
                row[2],
                rut,
                row[4],
                inicio,
                fin,
                int(row[9])
            ))

        execute_batch(
            cursor,
            f"""
            INSERT INTO {SCHEMA}.sacel (
                tipo_marcacion,
                rut,
                nombre_trip,
                inicio_actividad,
                fin_actividad,
                numero_flota
            )
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING;
            """,
            registros,
            page_size=1000
        )

        conn.commit()

        print(f"[SACEL] Filas insertadas: {len(registros)} | Saltadas: {saltadas}")

        total_procesadas += len(registros)
        total_saltadas += saltadas

    print(f"[SACEL] FIN | Total procesadas: {total_procesadas} | Total saltadas: {total_saltadas}")

# ======================
# CARGA SCANIA
# ======================
def cargar_scania(cursor, conn):
    print("\n------------------------------------------------------------")
    print("[SCANIA] INICIO CARGA DE DATOS")
    print("------------------------------------------------------------")

    for archivo in sorted(SCANIA_CSV.iterdir()):
        if archivo.suffix.lower() != ".csv":
            continue

        source_name = archivo.name

        cursor.execute(
            f"SELECT 1 FROM {SCHEMA}.scania WHERE source_name=%s LIMIT 1;",
            (source_name,)
        )
        if cursor.fetchone():
            print(f"[SCANIA] OMITIDO (ya cargado): {source_name}")
            continue

        print(f"[SCANIA] Cargando archivo: {source_name}")

        df_raw = pd.read_csv(archivo, encoding="utf-8", sep=";", header=None)
        df = df_raw.iloc[6:].copy()

        for _, row in df.iterrows():
            cursor.execute(f"""
                INSERT INTO {SCHEMA}.scania (
                    vehiculo, distancia_km, tiempo_motor,
                    ralenti_pct, exceso_velocidad_pct, inercia_pct,
                    consumo_diesel_litros, consumo_diesel_ralenti_litros,
                    tiempo_motor_ralenti, velocidad_media_kmh, source_name
                )
                VALUES (
                    %s,%s,%s::interval,%s,%s,%s,
                    %s,%s,%s::interval,%s,%s
                );
            """, (
                row[1],
                to_numeric(row[6]),
                to_interval(row[7]),
                to_numeric(row[14]),
                to_numeric(row[16]),
                to_numeric(row[18]),
                to_numeric(row[24]),
                to_numeric(row[25]),
                to_interval(row[36]),
                to_numeric(row[42]),
                source_name
            ))

        conn.commit()
        print(f"[SCANIA] OK: {source_name}")

    print("[SCANIA] FIN DE CARGA")

# ======================
# CARGA EXCESOS
# ======================
def cargar_excesos(cursor, conn):
    print("\n------------------------------------------------------------")
    print("[EXCESOS] INICIO CARGA DE DATOS")
    print("------------------------------------------------------------")

    for archivo in sorted(EXCESO_CSV.glob("*.csv")):
        source_name = archivo.name

        cursor.execute(
            f"SELECT 1 FROM {SCHEMA}.excesos_velocidad WHERE source_name=%s LIMIT 1;",
            (source_name,)
        )
        if cursor.fetchone():
            print(f"[EXCESOS] OMITIDO (ya cargado): {source_name}")
            continue

        print(f"[EXCESOS] Cargando archivo: {source_name}")

        df = pd.read_csv(
            archivo,
            sep=",",
            encoding="utf-8-sig",
            engine="python"
        )

        df = normalizar_columnas(df)

        df_final = pd.DataFrame({
            "numero_flota": df["n_flota"].apply(to_int),
            "tipo_evento": df["tipo_evento"],
            "inicio_evento": pd.to_datetime(df["inicio_evento"], dayfirst=True, errors="coerce"),
            "fin_evento": pd.to_datetime(df["fin_evento"], dayfirst=True, errors="coerce"),
            "duracion_seg": df["dur_seg"].apply(to_int),
            "limite_velocidad": df["lim_v_v_ini"].apply(to_int),
            "exceso_velocidad": df["exc_v_v_fin"].apply(to_int),
            "odometro": df["odometro"].apply(to_int),
            "rut_conductor": df["rut_conductor"].apply(limpiar_rut),
            "nombre_conductor": df["nombre_conductor"],
            "source_name": source_name
        })

        registros = list(df_final.itertuples(index=False, name=None))

        execute_batch(
            cursor,
            f"""
            INSERT INTO {SCHEMA}.excesos_velocidad (
                numero_flota, tipo_evento,
                inicio_evento, fin_evento,
                duracion_seg, limite_velocidad,
                exceso_velocidad, odometro,
                rut_conductor, nombre_conductor, source_name
            )
            VALUES (
                %s::bigint,%s,%s,%s,
                %s::bigint,%s::bigint,%s::bigint,%s::bigint,
                %s,%s,%s
            )
            ON CONFLICT (source_name, inicio_evento, numero_flota) DO NOTHING;
            """,
            registros,
            page_size=1000
        )

        conn.commit()
        print(f"[EXCESOS] OK: {source_name}")

    print("[EXCESOS] FIN DE CARGA")

# ======================
# MAIN
# ======================
def build_parser():
    parser = argparse.ArgumentParser(description="Carga CSV a la base de datos por fuente.")
    parser.add_argument(
        "--fuente",
        choices=("todo", "sacel", "scania", "excesos"),
        default="todo",
        help="Fuente a cargar. Por defecto carga todo.",
    )
    return parser

def main():
    args = build_parser().parse_args()
    conn, cursor = conectar_bd()
    try:
        if args.fuente in ("todo", "sacel"):
            cargar_sacel(cursor, conn)
        if args.fuente in ("todo", "scania"):
            cargar_scania(cursor, conn)
        if args.fuente in ("todo", "excesos"):
            cargar_excesos(cursor, conn)
    finally:
        cursor.close()
        conn.close()
        print("\n[DB] Conexion cerrada correctamente\n")

if __name__ == "__main__":
    main()
