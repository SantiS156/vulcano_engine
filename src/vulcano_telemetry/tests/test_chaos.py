import time
import pytest
import boto3
from botocore.exceptions import ClientError

from src.vulcano_telemetry.webhook_crypto import generate_signature
from src.vulcano_telemetry.exceptions import (
    WebhookSignatureError,
    WebhookTimestampError,
    SQSConnectionError,
)
from src.vulcano_telemetry.core_sqs import get_sqs_client, send_event, receive_events


@pytest.fixture
def localstack_sqs():
    endpoint = "http://localhost:4566"
    try:
        client = get_sqs_client(endpoint)
        client.list_queues()
        return client
    except Exception as exc:
        pytest.skip(f"LocalStack no está disponible en {endpoint}: {exc}")


def test_invalid_signature_rejection():
    secret = "clave-secreta-super-larga-123456"
    timestamp = int(time.time())
    payload = b'{"event":"payment.successful","amount":100.50}'
    
    valid_signature = generate_signature(secret, timestamp, payload)
    corrupted_signature = "a" * len(valid_signature)
    
    header_value = f"t={timestamp},v1={corrupted_signature}"
    
    from src.vulcano_telemetry.webhook_crypto import verify_signature
    
    with pytest.raises(WebhookSignatureError):
        verify_signature(secret, header_value, payload, tolerance_sec=300)


def test_expired_timestamp_replay_attack():
    secret = "clave-secreta-super-larga-123456"
    old_timestamp = int(time.time()) - 3600
    payload = b'{"event":"payment.expired","amount":50.00}'
    
    signature = generate_signature(secret, old_timestamp, payload)
    header_value = f"t={old_timestamp},v1={signature}"
    
    from src.vulcano_telemetry.webhook_crypto import verify_signature
    
    with pytest.raises(WebhookTimestampError):
        verify_signature(secret, header_value, payload, tolerance_sec=300)


def test_poison_message_dlq_redirection(localstack_sqs):
    queue_name_base = f"vulcano-test-{int(time.time())}"
    main_queue_name = f"{queue_name_base}-queue"
    dlq_name = f"{queue_name_base}-dlq"
    
    try:
        dlq_response = localstack_sqs.create_queue(QueueName=dlq_name)
        dlq_arn = localstack_sqs.get_queue_attributes(
            QueueUrl=dlq_response["QueueUrl"], AttributeNames=["QueueArn"]
        )["Attributes"]["QueueArn"]
        
        redrive_policy = json.dumps({
            "deadLetterTargetArn": dlq_arn,
            "maxReceiveCount": "1"
        })
        
        main_queue_response = localstack_sqs.create_queue(
            QueueName=main_queue_name,
            Attributes={"RedrivePolicy": redrive_policy}
        )
        main_queue_url = main_queue_response["QueueUrl"]
        
        poison_payload = {"error": "corrupted_payload_structure"}
        send_event(localstack_sqs, main_queue_url, poison_payload, trace_id="chaos-trace-01")
        
        messages = receive_events(localstack_sqs, main_queue_url, wait_time=2)
        assert len(messages) == 1
        
        msg = messages[0]
        assert msg["Body"] is not None
        
    finally:
        try:
            q_url = localstack_sqs.get_queue_url(QueueName=main_queue_name)["QueueUrl"]
            localstack_sqs.delete_queue(QueueUrl=q_url)
        except Exception:
            pass
        try:
            dlq_url = localstack_sqs.get_queue_url(QueueName=dlq_name)["QueueUrl"]
            localstack_sqs.delete_queue(QueueUrl=dlq_url)
        except Exception:
            pass
