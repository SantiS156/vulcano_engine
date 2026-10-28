"""Sistema de logging estructurado para Vulcano Pay.

Incluye formato JSON, excepciones recursivas, escritura no bloqueante
y rotación de archivos con compresión Gzip.
"""

import gzip
import json
import logging
import os
import queue
import shutil
import threading
import copy

from datetime import datetime, timezone
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path

class PreservingQueueHandler(QueueHandler):
    """Encola registros conservando los datos de las excepciones."""

    def prepare(self, record):
        prepared = copy.copy(record)
        prepared.message = record.getMessage()
        prepared.msg = prepared.message
        prepared.args = None
        prepared.exc_text = record.exc_text
        # Conservar exc_info para que el formateador pueda serializar
        # la excepción en el hilo del QueueListener.
        return prepared

class AsyncJSONFormatter(logging.Formatter):
    """Convierte los registros de logging a JSON estructurado."""

    def format(self, record: logging.LogRecord) -> str:
        """Serializa un LogRecord y sus excepciones en formato JSON."""

        timestamp = datetime.fromtimestamp(
            record.created, tz=timezone.utc
        ).isoformat(timespec="milliseconds").replace("+00:00", "Z")

        data = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "process": record.process,
            "threadName": record.threadName,
        }

        # Incorporar identificadores de trazabilidad si existen.
        for field in ("TraceId", "MessageId", "WebhookId",
                      "X-Webhook-Signature"):
            value = getattr(record, field, None)
            if value is not None:
                data[field] = value

        # Conservar los atributos adicionales del registro.
        standard_fields = set(
            logging.makeLogRecord({}).__dict__.keys()
        )
        excluded_fields = standard_fields | {
            "message", "asctime", "TraceId", "MessageId",
            "WebhookId", "X-Webhook-Signature",
        }

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in excluded_fields
        }

        if extras:
            data["extra"] = self._json_safe(extras)

        # Serializar las excepciones, incluidos ExceptionGroup y sus notas.
        if record.exc_info:
            data["exception"] = self._serialize_exception(
                record.exc_info[1]
            )

        return json.dumps(
            data, ensure_ascii=False, default=self._json_safe
        )

    @classmethod
    def _serialize_exception(cls, exc: BaseException) -> dict:
        """Representa recursivamente una excepción y sus notas."""

        result = {
            "type": type(exc).__name__,
            "message": str(exc),
            "notes": list(getattr(exc, "__notes__", [])),
        }

        if exc.__traceback__ is not None:
            import traceback

            result["traceback"] = "".join(
                traceback.format_exception(
                    type(exc), exc, exc.__traceback__
                )
            )

        if isinstance(exc, BaseExceptionGroup):
            result["exceptions"] = [
                cls._serialize_exception(child)
                for child in exc.exceptions
            ]

        if exc.__cause__ is not None:
            result["cause"] = cls._serialize_exception(exc.__cause__)
        elif exc.__context__ is not None:
            result["context"] = cls._serialize_exception(
                exc.__context__
            )

        return result

    @staticmethod
    def _json_safe(value):
        """Convierte valores no serializables a representaciones seguras."""

        if isinstance(value, dict):
            return {
                str(key): AsyncJSONFormatter._json_safe(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [
                AsyncJSONFormatter._json_safe(item)
                for item in value
            ]

        if value is None or isinstance(
            value, (str, int, float, bool)
        ):
            return value

        return repr(value)


def _gzip_namer(filename: str) -> str:
    """Añade .gz al nombre del archivo rotado."""

    return filename + ".gz"


def _gzip_rotator(source: str, destination: str) -> None:
    """Comprime el archivo rotado y elimina el original tras comprimirlo."""

    temporary = destination + ".tmp"

    try:
        with open(source, "rb") as original:
            with gzip.open(temporary, "wb") as compressed:
                shutil.copyfileobj(original, compressed)

        # Publicar el comprimido mediante un renombrado atómico.
        os.replace(temporary, destination)
        os.remove(source)

    except OSError:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise


class LoggingEngine:
    """Gestiona el pipeline de logging asíncrono de Vulcano."""

    def __init__(
        self,
        log_file: str = "logs/vulcano.log",
        level: int = logging.INFO,
    ):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        self.log_queue = queue.Queue(-1)


        self.file_handler = RotatingFileHandler(
            filename=self.log_file,
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        self.file_handler.setFormatter(AsyncJSONFormatter())
        self.file_handler.namer = _gzip_namer
        self.file_handler.rotator = _gzip_rotator

        self.listener = QueueListener(
            self.log_queue,
            self.file_handler,
            respect_handler_level=True,
        )

        self.logger = logging.getLogger("vulcano")
        self.logger.setLevel(level)
        self.logger.propagate = False


        # Evitar acumular handlers al inicializar varias veces.
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
            handler.close()

        self.queue_handler = PreservingQueueHandler(self.log_queue)
        self.queue_handler.setLevel(level)
        self.logger.addHandler(self.queue_handler)

        self._started = False
        self._lock = threading.Lock()

    def start(self) -> logging.Logger:
        """Inicia el hilo que escribe los logs."""

        with self._lock:
            if not self._started:
                self.listener.start()
                self._started = True

        return self.logger

    def stop(self) -> None:
        """Detiene el listener y libera sus recursos de forma ordenada."""

        with self._lock:
            if self._started:
                self.listener.stop()
                self._started = False

            self.logger.removeHandler(self.queue_handler)
            self.queue_handler.close()
            self.file_handler.close()


    def __enter__(self):
        self.start()
        return self.logger

    def __exit__(self, exc_type, exc_value, traceback_obj):
        self.stop()


