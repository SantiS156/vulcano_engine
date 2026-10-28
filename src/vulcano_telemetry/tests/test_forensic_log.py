import gzip
import json
import logging
import os
from pathlib import Path
import pytest

from src.vulcano_telemetry.logging_engine import LoggingEngine


def test_async_json_formatter_structure(tmp_path):
    log_file = tmp_path / "logs" / "vulcano_test.log"
    
    engine = LoggingEngine(log_file=str(log_file), level=logging.INFO)
    logger = engine.start()
    
    try:
        logger.info(
            "Transacción de pago procesada con éxito",
            extra={
                "TraceId": "tr-abc-123-xyz",
                "MessageId": "msg-sqs-789",
                "WebhookId": "wh-456",
                "X-Webhook-Signature": "t=1700000000,v1=mocksignature",
                "CustomData": {"monto": 1500.0}
            }
        )
    finally:
        engine.stop()
        
    assert log_file.exists()
    
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    assert len(lines) > 0
    
    log_record = json.loads(lines[-1].strip())
    
    assert log_record["level"] == "INFO"
    assert log_record["message"] == "Transacción de pago procesada con éxito"
    assert log_record["TraceId"] == "tr-abc-123-xyz"
    assert log_record["MessageId"] == "msg-sqs-789"
    assert log_record["WebhookId"] == "wh-456"
    assert log_record["X-Webhook-Signature"] == "t=1700000000,v1=mocksignature"
    assert "timestamp" in log_record
    assert log_record["extra"]["CustomData"]["monto"] == 1500.0


def test_gzip_rotation_and_decompression(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    source_log = logs_dir / "vulcano.log"
    compressed_log = logs_dir / "vulcano.log.gz"
    
    sample_data = json.dumps({
        "timestamp": "2026-03-30T12:00:00.000Z",
        "level": "ERROR",
        "message": "Fallo crítico simulado para prueba forense"
    }) + "\n"
    
    source_log.write_text(sample_data, encoding="utf-8")
    
    with open(source_log, "rb") as f_in:
        with gzip.open(compressed_log, "wb") as f_out:
            f_out.writelines(f_in)
            
    source_log.unlink()
    
    assert compressed_log.exists()
    assert not source_log.exists()
    
    with gzip.open(compressed_log, "rt", encoding="utf-8") as f_in:
        decompressed_content = f_in.read()
        
    parsed_json = json.loads(decompressed_content.strip())
    assert parsed_json["level"] == "ERROR"
    assert "Fallo crítico simulado" in parsed_json["message"]
