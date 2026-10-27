import hashlib
import hmac
import time
from .exceptions import WebhookTimestampError, WebhookSignatureError

def generate_signature(secret: str, timestamp: int, payload_bytes: bytes) -> str:
    byte_set = secret.encode("utf-8")
    mensaje_unido = f"{timestamp}.".encode("utf-8") + payload_bytes

    firma = hmac.new(byte_set, mensaje_unido, hashlib.sha256).hexdigest()
    return firma

def verify_signature(secret: str, header_value: str, payload_bytes: bytes, tolerance_sec: int = 300) -> bool:

    partes = header_value.split(",")

    parte_t = partes[0].split("=")
    parte_v1 = partes[1].split("=")

    timestamp = int(parte_t[1])
    firma_recibida = parte_v1[1]

    ahora = time.time()
    diferencia = abs(ahora - timestamp)

    if diferencia > tolerance_sec:
        raise WebhookTimestampError("Timestamp fuera de la tolerancia")
    
    firma_calculada = generate_signature(secret, timestamp, payload_bytes)

    if not hmac.compare_digest(firma_recibida, firma_calculada):
        raise WebhookSignatureError("Firma HMAC no válida")
    
    return True



