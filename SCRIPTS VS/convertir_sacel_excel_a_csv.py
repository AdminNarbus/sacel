import os
import re
import shutil
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pandas as pd

from common import repo_path

SOFFICE = os.environ.get("SOFFICE_PATH") or shutil.which("soffice") or r"C:\Program Files\LibreOffice\program\soffice.exe"

BASE = repo_path()
SACEL_EXCEL = BASE / "SacelExcel"
SACEL_CSV = BASE / "SacelCSV"
SACEL_CSV.mkdir(exist_ok=True)

MESES_ES = {
    "Enero": 1,
    "Febrero": 2,
    "Marzo": 3,
    "Abril": 4,
    "Mayo": 5,
    "Junio": 6,
    "Julio": 7,
    "Agosto": 8,
    "Septiembre": 9,
    "Octubre": 10,
    "Noviembre": 11,
    "Diciembre": 12,
}

MESES_ES_INV = {v: k for k, v in MESES_ES.items()}


def es_xls_valido(path: Path) -> bool:
    return path.suffix.lower() == ".xls" and not path.name.startswith("~$")


def csv_mas_reciente(carpeta: Path) -> Path | None:
    csvs = list(carpeta.glob("*.csv"))
    if not csvs:
        return None
    return max(csvs, key=lambda p: p.stat().st_mtime)


def convertir_con_libreoffice(excel: Path, outdir: Path) -> Path:
    subprocess.run([
        SOFFICE,
        "--headless",
        "--nologo",
        "--nofirststartwizard",
        "--convert-to",
        "csv",
        "--outdir",
        str(outdir),
        str(excel),
    ], check=True)

    generado = csv_mas_reciente(outdir)
    if not generado:
        raise RuntimeError("LibreOffice no genero CSV")
    return generado


def convertir_con_pandas(excel: Path, destino_temporal: Path) -> Path:
    # Algunos reportes llegan como .xlsx pero con extension .xls.
    with tempfile.TemporaryDirectory() as tmp:
        copia_xlsx = Path(tmp) / f"{excel.stem}.xlsx"
        shutil.copy2(excel, copia_xlsx)
        df = pd.read_excel(copia_xlsx, engine="openpyxl", header=None)

    df.to_csv(destino_temporal, index=False, header=False, encoding="latin1", errors="replace")
    return destino_temporal


def columna_excel_a_indice(referencia: str) -> int:
    letras = re.sub(r"[^A-Z]", "", referencia.upper())
    indice = 0
    for letra in letras:
        indice = indice * 26 + (ord(letra) - ord("A") + 1)
    return indice - 1


def texto_celda(celda, ns):
    tipo = celda.attrib.get("t")
    if tipo == "inlineStr":
        return "".join(celda.itertext()).strip()

    valor = celda.find("main:v", ns)
    if valor is None or valor.text is None:
        return ""
    return valor.text.strip()


def convertir_xlsx_xml_a_csv(excel: Path, destino_temporal: Path) -> Path:
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    filas_csv = []

    with zipfile.ZipFile(excel) as archivo_zip:
        xml = archivo_zip.read("xl/worksheets/sheet1.xml")

    root = ET.fromstring(xml)
    for fila in root.findall(".//main:sheetData/main:row", ns):
        valores = []
        for celda in fila.findall("main:c", ns):
            indice = columna_excel_a_indice(celda.attrib.get("r", "A1"))
            while len(valores) <= indice:
                valores.append("")
            valores[indice] = texto_celda(celda, ns)
        filas_csv.append(valores)

    max_columnas = max((len(fila) for fila in filas_csv), default=0)
    filas_csv = [fila + [""] * (max_columnas - len(fila)) for fila in filas_csv]
    pd.DataFrame(filas_csv).to_csv(destino_temporal, index=False, header=False, encoding="latin1", errors="replace")
    return destino_temporal


def extraer_mes_anio(nombre: str) -> tuple[int, int] | None:
    for mes in MESES_ES:
        match = re.search(rf"{mes}[_\-\s](20\d{{2}})", nombre, re.IGNORECASE)
        if match:
            return MESES_ES[mes], int(match.group(1))
    return None


def main():
    print("\n============================================================")
    print("[SACEL] PROCESO DE CONVERSION EXCEL A CSV")
    print("============================================================")

    hoy = date.today()
    conv_sacel = 0
    skip_sacel = 0
    fail_sacel = 0

    for excel in sorted(SACEL_EXCEL.iterdir()):
        if not es_xls_valido(excel):
            continue

        extraido = extraer_mes_anio(excel.name)
        if not extraido:
            print(f"[SACEL] ADVERTENCIA: No se detecta mes/anio -> {excel.name}")
            skip_sacel += 1
            continue

        mes, anio = extraido
        nombre_csv = f"{MESES_ES_INV[mes]}_{anio}.csv"
        destino = SACEL_CSV / nombre_csv
        es_mes_actual = mes == hoy.month and anio == hoy.year

        if destino.exists() and not es_mes_actual:
            print(f"[SACEL] OMITIDO (mes cerrado): {nombre_csv}")
            skip_sacel += 1
            continue

        accion = "REEMPLAZANDO" if es_mes_actual else "CONVIRTIENDO"
        print(f"[SACEL] {accion}: {excel.name} -> {nombre_csv}")

        try:
            with tempfile.TemporaryDirectory(dir=SACEL_CSV) as tmp:
                tmp_dir = Path(tmp)
                destino_temporal = tmp_dir / nombre_csv

                try:
                    generado = convertir_con_libreoffice(excel, tmp_dir)
                    generado.rename(destino_temporal)
                except Exception as libreoffice_exc:
                    print(f"[SACEL] LibreOffice fallo, probando fallback pandas/openpyxl: {libreoffice_exc}")
                    try:
                        convertir_con_pandas(excel, destino_temporal)
                    except Exception as pandas_exc:
                        print(f"[SACEL] pandas/openpyxl fallo, extrayendo XML interno: {pandas_exc}")
                        convertir_xlsx_xml_a_csv(excel, destino_temporal)

                os.replace(destino_temporal, destino)

            conv_sacel += 1
            print(f"[SACEL] OK: {nombre_csv}")
        except Exception as exc:
            print(f"[SACEL] ERROR: {excel.name} -> {exc}")
            fail_sacel += 1

    print("\n============================================================")
    print("[SACEL] RESUMEN FINAL")
    print("============================================================")
    print(f"[SACEL] Convertidos/Reemplazados : {conv_sacel}")
    print(f"[SACEL] Omitidos                : {skip_sacel}")
    print(f"[SACEL] Fallidos                : {fail_sacel}")
    print("============================================================")


if __name__ == "__main__":
    main()
