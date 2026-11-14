
import json
import time
import uuid

import pytest
from botocore.exceptions import ClientError

from vulcano_telemetry.webhook_crypto import (
    generate_signature,
    verify_signature
)

from vulcano_telemetry.exceptions import (
    WebhookSignatureError,
    WebhookTimestampError,
    SQSConnectionError
)

from vulcano_telemetry.core_sqs import (
    get_sqs_client,
    send_event
)


SECRET_KEY = "secret-key-for-testing"
PAYLOAD = b'{"payment_id":"PAY-001","status":"approved"}'


@pytest.fixture
def localstack_sqs():
    """
    Comprueba la conexión con LocalStack.
    Si el servicio no está disponible, omite las pruebas
    que necesitan una instancia real de SQS.
    """
    client = get_sqs_client(
        endpoint_url="http://localhost:4566"
    )

    try:
        client.list_queues()

    except Exception as error:
        pytest.skip(
            f"LocalStack no está disponible: {error}"
        )

    return client


def test_invalid_signature_rejection():
    """
    Comprueba que una firma HMAC modificada sea rechazada.
    """
    timestamp = int(time.time())

    valid_signature = generate_signature(
        SECRET_KEY,
        timestamp,
        PAYLOAD
    )

    invalid_signature = (
        valid_signature.rsplit("v1=", 1)[0]
        + "v1="
        + ("0" * 64)
    )

    with pytest.raises(WebhookSignatureError):
        verify_signature(
            SECRET_KEY,
            invalid_signature,
            PAYLOAD,
            tolerance_sec=300
        )


def test_valid_signature_accepted():
    """
    Comprueba que una firma HMAC válida y vigente sea aceptada.
    """
    timestamp = int(time.time())

    signature = generate_signature(
        SECRET_KEY,
        timestamp,
        PAYLOAD
    )

    verify_signature(
        SECRET_KEY,
        signature,
        PAYLOAD,
        tolerance_sec=300
    )


def test_expired_timestamp_replay_attack():
    """
    Comprueba que se rechace una firma con timestamp vencido.
    Simula un intento de reutilización de una solicitud antigua.
    """
    old_timestamp = int(time.time()) - 3600

    old_signature = generate_signature(
        SECRET_KEY,
        old_timestamp,
        PAYLOAD
    )

    with pytest.raises(WebhookTimestampError):
        verify_signature(
            SECRET_KEY,
            old_signature,
            PAYLOAD,
            tolerance_sec=300
        )


def test_sqs_publication_failure():
    """
    Comprueba que un error de publicación en SQS se convierta
    en SQSConnectionError y conserve su causa original.
    """

    class FakeSQSClient:
        def send_message(self, **kwargs):
            raise ClientError(
                {
                    "Error": {
                        "Code": "ServiceUnavailable",
                        "Message": "Fallo simulado de SQS"
                    }
                },
                "SendMessage"
            )

    fake_client = FakeSQSClient()

    with pytest.raises(SQSConnectionError) as captured:
        send_event(
            sqs_client=fake_client,
            queue_url="http://localhost:4566/000000000000/test-queue",
            event_data={
                "payment_id": "PAY-001",
                "status": "approved"
            },
            trace_id="trace-chaos-001"
        )

    error = captured.value

    assert isinstance(error.__cause__, ClientError)

    assert any(
        "QueueUrl intentada" in note
        for note in getattr(error, "__notes__", [])
    )


def test_sqs_invalid_message_redrive_to_dlq(localstack_sqs):
    """
    Comprueba el mecanismo RedrivePolicy de SQS en LocalStack.
    Envía un mensaje JSON inválido, lo recibe sin eliminarlo
    y verifica que termine en la Dead Letter Queue.

    Esta prueba verifica el redrive de SQS, no la ejecución
    del worker real de Vulcano Pay.
    """
    client = localstack_sqs

    unique_id = uuid.uuid4().hex[:10]

    main_queue_name = f"chaos-main-{unique_id}"
    dlq_name = f"chaos-dlq-{unique_id}"

    main_queue_url = None
    dlq_url = None

    try:
        dlq_response = client.create_queue(
            QueueName=dlq_name
        )

        dlq_url = dlq_response["QueueUrl"]

        dlq_attributes = client.get_queue_attributes(
            QueueUrl=dlq_url,
            AttributeNames=["QueueArn"]
        )

        dlq_arn = dlq_attributes["Attributes"]["QueueArn"]

        redrive_policy = {
            "deadLetterTargetArn": dlq_arn,
            "maxReceiveCount": "1"
        }

        main_response = client.create_queue(
            QueueName=main_queue_name,
            Attributes={
                "VisibilityTimeout": "1",
                "RedrivePolicy": json.dumps(redrive_policy)
            }
        )

        main_queue_url = main_response["QueueUrl"]

        invalid_body = '{"event":"payment.failed"'

        client.send_message(
            QueueUrl=main_queue_url,
            MessageBody=invalid_body
        )

        first_receive = client.receive_message(
            QueueUrl=main_queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=1,
            AttributeNames=["ApproximateReceiveCount"]
        )

        messages = first_receive.get("Messages", [])

        assert len(messages) == 1
        assert messages[0]["Body"] == invalid_body

        receive_count = int(
            messages[0]["Attributes"]["ApproximateReceiveCount"]
        )

        assert receive_count == 1

        time.sleep(2)

        for _ in range(5):
            response = client.receive_message(
                QueueUrl=main_queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=1,
                AttributeNames=["ApproximateReceiveCount"]
            )

            if not response.get("Messages"):
                break

            time.sleep(2)

       
        dlq_message = None

        for _ in range(10):
            response = client.receive_message(
                QueueUrl=dlq_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=1
            )

            received_messages = response.get("Messages", [])
            if received_messages:
                dlq_message = received_messages[0]
                break
        assert dlq_message is not None, (
            "El mensaje no apareció en la Dead Letter Queue."
        )
        assert dlq_message["Body"] == invalid_body

    finally:       
        if main_queue_url:
            client.delete_queue(
                QueueUrl=main_queue_url
            )

        if dlq_url:
            client.delete_queue(
                QueueUrl=dlq_url
            )
