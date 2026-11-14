
import gzip
import json
import logging
from datetime import datetime, timedelta

from logging_engine import LoggingEngine


def test_async_json_formatter_structure(tmp_path):
   
    log_file = tmp_path / "vulcano.log"

    engine = LoggingEngine(
        log_file=str(log_file),
        level=logging.INFO
    )

    logger = engine.start()

    try:
        logger.info(
            "Evento de pago procesado",
            extra={
                "TraceId": "trace-test-001",
                "MessageId": "message-test-001",
                "WebhookId": "webhook-test-001",
                "X-Webhook-Signature": "firma-simulada",
                "CustomData": {
                    "payment_id": "PAY-001",
                    "status": "approved"
                }
            }
        )
    finally:
        engine.stop()

    assert log_file.exists()

    with open(log_file, "r", encoding="utf-8") as file:
        lines = file.readlines()

    assert lines, "No se generaron registros de log."

    record = json.loads(lines[-1])

    assert record["level"] == "INFO"
    assert record["message"] == "Evento de pago procesado"

    assert record["TraceId"] == "trace-test-001"
    assert record["MessageId"] == "message-test-001"
    assert record["WebhookId"] == "webhook-test-001"
    assert record["X-Webhook-Signature"] == "firma-simulada"

    assert record["extra"]["CustomData"]["payment_id"] == "PAY-001"
    assert record["extra"]["CustomData"]["status"] == "approved"

    timestamp = record["timestamp"]

    assert timestamp.endswith("Z")

    parsed_timestamp = datetime.fromisoformat(
        timestamp.replace("Z", "+00:00")
    )

    assert parsed_timestamp.utcoffset() == timedelta(0)


def test_exception_group_logging(tmp_path):
    log_file = tmp_path / "vulcano.log"

    engine = LoggingEngine(
        log_file=str(log_file),
        level=logging.INFO
    )

    logger = engine.start()

    try:
        try:
            try:
                raise ValueError("causa-raiz-simulada")

            except ValueError as cause:
                group = ExceptionGroup(
                    "fallos agrupados del procesamiento",
                    [
                        RuntimeError("fallo de entrega HTTP"),
                        RuntimeError("fallo de procesamiento")
                    ]
                )

                group.add_note(
                    "nota-forense: trace-id-123"
                )

                raise group from cause

        except ExceptionGroup:
            logger.exception(
                "Se produjo un error agrupado durante el procesamiento"
            )

    finally:
        engine.stop()

    assert log_file.exists()

    with open(log_file, "r", encoding="utf-8") as file:
        lines = file.readlines()

    assert lines

    record = json.loads(lines[-1])

    exception = record["exception"]

    assert exception["type"] == "ExceptionGroup"
    assert "fallos agrupados" in exception["message"]

    assert exception["traceback"]

    assert "nota-forense: trace-id-123" in exception["notes"]

    assert len(exception["exceptions"]) == 2

    assert exception["exceptions"][0]["type"] == "RuntimeError"
    assert exception["exceptions"][1]["type"] == "RuntimeError"

    assert exception["cause"]["type"] == "ValueError"
    assert exception["cause"]["message"] == "causa-raiz-simulada"


def test_real_gzip_rotation_and_decompression(tmp_path):
    log_file = tmp_path / "vulcano.log"

    engine = LoggingEngine(
        log_file=str(log_file),
        level=logging.INFO
    )

    logger = engine.start()

    first_payload = "A" * (1500 * 1024)

    second_payload = "B" * (1024 * 1024)

    try:
        logger.info(
            "REGISTRO ORIGINAL PARA ROTACION",
            extra={
                "CustomData": {
                    "payload": first_payload
                }
            }
        )

        logger.info(
            "SEGUNDO REGISTRO PARA FORZAR ROTACION",
            extra={
                "CustomData": {
                    "payload": second_payload
                }
            }
        )

    finally:
        engine.stop()

    assert log_file.exists()

    gzip_backups = list(
        tmp_path.glob("vulcano.log.*.gz")
    )

    assert gzip_backups, (
        "No se generaron archivos de respaldo GZIP."
    )

    assert len(gzip_backups) <= 3

    original_record_found = False

    for backup in gzip_backups:
        with gzip.open(
            backup,
            "rt",
            encoding="utf-8"
        ) as compressed_file:

            for line in compressed_file:
                record = json.loads(line)

                if record["message"] == (
                    "REGISTRO ORIGINAL PARA ROTACION"
                ):
                    original_record_found = True

                    recovered_payload = (
                        record["extra"]["CustomData"]["payload"]
                    )

                    assert recovered_payload == first_payload

    assert original_record_found, (
        "No se encontró el registro original dentro del respaldo GZIP."
    )
