import boto3
import json
from botocore.exceptions import ClientError
from .exceptions import SQSConnectionError
from datetime import datetime, timezone

def get_sqs_client(endpoint_url: str = "http://localhost:4566"):
    return boto3.client("sqs",endpoint_url= endpoint_url, region_name ="us-east-1", aws_access_key_id ="test", aws_secret_access_key ="test", )


def send_event(
    sqs_client,
    queue_url,
    event_data,
    trace_id="trace-default",
    event_topic="telemetry",
    timestamp=None,
):
    """Publica un evento en SQS y devuelve su MessageId."""

    cuerpo_json = json.dumps(event_data)
    if timestamp is None:
        timestamp = (
            datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
    )
    etiquetas = {
        "TraceId": {
            "DataType": "String",
            "StringValue": trace_id,
        },
        "EventTopic": {
            "DataType": "String",
            "StringValue": event_topic,
        },
        "Timestamp": {
            "DataType": "String",
            "StringValue": timestamp,
        },
    }

    try:
        response = sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=cuerpo_json,
            MessageAttributes=etiquetas,
        )
        return response.get("MessageId", "")

    except ClientError as err:
        sqs_err = SQSConnectionError(
            "Error al publicar el evento en SQS"
        )
        sqs_err.add_note(f"QueueUrl intentada: {queue_url}")
        raise sqs_err from err




def receive_events(
    sqs_client,
    queue_url: str,
    wait_time: int = 10,
    max_messages: int = 5,
    visibility_timeout: int = 30,
):
    """Recibe mensajes de SQS mediante long polling."""

    try:
        respuesta = sqs_client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_time,
            VisibilityTimeout=visibility_timeout,
            MessageAttributeNames=["All"],
        )
        return respuesta.get("Messages", [])

    except ClientError as err:
        sqs_err = SQSConnectionError(
            "Error de conexión al consumidor de eventos de SQS"
        )
        sqs_err.add_note(f"QueueUrl intentada: {queue_url}")
        raise sqs_err from err
