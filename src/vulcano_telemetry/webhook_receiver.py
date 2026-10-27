import os
import json
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from .webhook_crypto import verify_signature
from .exceptions import WebhookSignatureError, WebhookTimestampError
from .core_sqs import get_sqs_client, send_event


app = FastAPI()

def publicar_evento(event_data: dict):
    sqs_client = get_sqs_client()
    queue_url = sqs_client.get_queue_url(QueueName="vulcano-events-queue")["QueueUrl"]

    send_event(
        sqs_client=sqs_client,
        queue_url=queue_url,
        event_data=event_data,)


@app.post("/webhook", status_code=202)
async def recibir_webhook(
    request: Request,
    background_tasks: BackgroundTasks,):
    payload_bytes = await request.body()
    header_value = request.headers.get("X-Webhook-Signature")

    if not header_value:
        raise HTTPException(
            status_code=401,
            detail="Falta la firma",)

    secret = os.environ.get("WEBHOOK_SECRET")

    if not secret:
        raise HTTPException(
            status_code=500,
            detail="El secreto del webhook no está configurado",)

    try:
        verify_signature(secret, header_value, payload_bytes)
    except (WebhookSignatureError, WebhookTimestampError) as error:
        raise HTTPException(
            status_code=401,
            detail=str(error),)
    except (ValueError, IndexError, TypeError):
        raise HTTPException(status_code=401, detail="Cabecera de firma inválida",)

    try:
        event_data = json.loads(payload_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="El cuerpo del webhook no contiene JSON válido",)

    if not isinstance(event_data, dict):
        raise HTTPException(status_code=400,
            detail="El evento debe ser un objeto JSON",)

    background_tasks.add_task(publicar_evento, event_data)

    return {"status": "accepted"}