from common import script_path
from pipeline_utils import espera, ejecutar, paso, titulo


SCRIPT_ROBOT_SACEL = script_path("robot_sacel.py")
SCRIPT_ROBOT_EXCESO = script_path("robot_exceso_velocidad.py")
SCRIPT_CONVERTIR_SACEL = script_path("convertir_sacel_excel_a_csv.py")
SCRIPT_SUBIR_BD = script_path("subir_csv_bd.py")
SCRIPT_ALERTA_WSP = script_path("alerta_wsp.py")


def main():
    titulo("PIPELINE SACEL")

    titulo("EXTRACTOR SACEL ACTIVIDADES")
    paso("Lanzando robot_sacel.py")
    ejecutar(SCRIPT_ROBOT_SACEL)
    espera(5)

    titulo("EXTRACTOR SACEL EXCESOS")
    paso("Lanzando robot_exceso_velocidad.py")
    ejecutar(SCRIPT_ROBOT_EXCESO)
    espera(5)

    titulo("CONVERSION SACEL")
    paso("Lanzando convertir_sacel_excel_a_csv.py")
    ejecutar(SCRIPT_CONVERTIR_SACEL)
    espera(5)

    titulo("CARGA BD SACEL")
    paso("Lanzando subir_csv_bd.py --fuente sacel")
    ejecutar(SCRIPT_SUBIR_BD, "--fuente", "sacel")
    espera(5)

    titulo("CARGA BD EXCESOS")
    paso("Lanzando subir_csv_bd.py --fuente excesos")
    ejecutar(SCRIPT_SUBIR_BD, "--fuente", "excesos")
    espera(5)

    titulo("ALERTA WHATSAPP SACEL")
    paso("Lanzando alerta_wsp.py sacel")
    ejecutar(SCRIPT_ALERTA_WSP, "sacel")
    espera(5)

    titulo("PIPELINE SACEL FINALIZADO")


if __name__ == "__main__":
    main()
