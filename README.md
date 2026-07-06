# Paquete Sacel

Este paquete contiene solo el flujo Sacel separado del proyecto principal.

## Ejecutar pipeline completo Sacel

```powershell
.\run_pipeline_sacel.bat
```

Equivalente a:

```powershell
python "SCRIPTS VS\pipeline_sacel.py"
```

## Pasos internos

1. `robot_sacel.py`: extractor de actividades Sacel. Descarga Excel en `SacelExcel/`.
2. `robot_exceso_velocidad.py`: extractor de excesos de velocidad. Genera CSV en `ExcesoVelocidadCSV/`.
3. `convertir_sacel_excel_a_csv.py`: convierte Excel Sacel a CSV en `SacelCSV/`.
4. `subir_csv_bd.py --fuente sacel`: carga actividades Sacel a la base de datos.
5. `subir_csv_bd.py --fuente excesos`: carga excesos a la base de datos.
6. `alerta_wsp.py sacel`: genera/envia alerta Sacel.

## Configuracion

Usa `.env` para secretos. Si falta, copia `.env.example` a `.env` y completa valores.
