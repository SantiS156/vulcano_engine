import argparse
import re
from urllib.parse import urlparse


def validar_timeout(valor):
    try:
        val_float = float(valor)
    except ValueError:
        raise argparse.ArgumentTypeError(f"El timeout debe ser numérico: '{valor}'")
    if val_float < 0.1 or val_float > 5.0: 
        raise argparse.ArgumentTypeError(f"El timeout debe estar entre 0.1 y 5.0 segundos. Recibido: {val_float}")
    return val_float

def parse_secret_key(valor):
    if len(valor) < 16:
        raise argparse.ArgumentTypeError(f"La clave secreta debe tener al menos 16 caracteres. Longitud recibida: {len(valor)}")
    return valor

def parse_queue_name(valor):
    patron = r"^vulcano-[a-z0-9-]+-queue$"
    if not re.match(patron, valor):
        raise argparse.ArgumentTypeError(f"Nombre de cola inválido '{valor}'. Debe seguir el patrón 'vulcano-<nombre>-queue' ")
    return valor

def parse_webhook_url(valor):
    parsed = urlparse(valor)
    if parsed.scheme not in ("http", "https"):
        raise argparse.ArgumentTypeError(f"URL de webhook inválida '{valor}'. Debe comenzar con http:// o https://")
    return valor