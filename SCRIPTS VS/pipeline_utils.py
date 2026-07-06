import os
import subprocess
import sys
import time


PYTHON = sys.executable


def separador():
    print("\n" + "=" * 60 + "\n")


def titulo(texto):
    separador()
    print(f"[PIPELINE] {texto}")
    separador()


def paso(texto):
    print(f">> {texto}")


def espera(segundos):
    print(f". Esperando {segundos} segundos.\n")
    time.sleep(segundos)


def ejecutar(script_path, *args, allow_failure=False):
    comando = [PYTHON, str(script_path), *args]
    try:
        subprocess.run(comando, check=True)
        return True
    except subprocess.CalledProcessError:
        if not allow_failure:
            raise
        print(f"[WARN] Fallo permitido: {script_path.name}")
        return False


def env_bool(nombre, default=False):
    valor = os.getenv(nombre)
    if valor is None:
        return default
    return valor.strip().lower() in ("true", "1", "yes")
