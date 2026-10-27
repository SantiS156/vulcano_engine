
class VulcanoError(Exception):
    """Excepción base (nunca hereda BaseExcepción)"""
    pass

class SQSConnectionError(VulcanoError):
    """Fallo de red con LocalStack / SQS"""
    pass

class QueueTimeoutError(VulcanoError):
    """Tiempo de espera agotado en la cola"""
    pass

class CorruptedMessageError(VulcanoError):
    """El cuerpo de mensaje SQS no es un JSON válido"""
    pass


class WebhookSignatureError(VulcanoError):
    """Firma HMAC-SHA256 no válida o ausente"""
    pass

class WebhookTimestampError(ValueError):
    """Ataque de replay / timestamp fuera de tolerancia"""
    pass

class WebhookDeliveryError(ValueError):
    """Fallo de HTTP POST al emisor"""
    pass

class WebhookSignatureError(VulcanoError):
    """Firma HMAC-SHA256 no válida o ausente"""
    pass