
"""CLI e integración del motor de eventos Vulcano Pay."""

import argparse
import asyncio
import hashlib
import hmac
import json
import logging
import time
import uvicorn

import requests

from .core_sqs import get_sqs_client, send_event, receive_events
from .exceptions import (
    SQSConnectionError,
    WebhookDeliveryError,
    WebhookSignatureError,
    WebhookTimestampError,
)
from .logging_engine import LoggingEngine
from .sanitizer import (
    parse_queue_name,
    parse_secret_key,
    parse_webhook_url,
)
from .webhook_crypto import generate_signature


def parse_wait_time(value: str) -> int:
    """Valida el Long Polling de SQS entre 1 y 20 segundos."""

    try:
        seconds = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "El tiempo de espera debe ser un entero."
        ) from exc

    if not 1 <= seconds <= 20:
        raise argparse.ArgumentTypeError(
            "WaitTimeSeconds debe estar entre 1 y 20."
        )

    return seconds


def build_parser() -> argparse.ArgumentParser:
    """Define los comandos de la aplicación."""

    parser = argparse.ArgumentParser(
        prog="vulcano",
        description="Motor de eventos Vulcano Pay",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    producer = subparsers.add_parser(
        "produce-sqs",
        help="Publica un evento en SQS",
    )
    producer.add_argument(
        "--queue",
        type=parse_queue_name,
        default="vulcano-events-queue",
    )
    producer.add_argument(
        "--message",
        required=True,
        help="Evento en formato JSON",
    )
    producer.add_argument(
        "--endpoint",
        default="http://localhost:4566",
    )

    receiver = subparsers.add_parser(
        "start-receiver",
        help="Inicia el servidor receptor HTTP",
    )
    receiver.add_argument("--host", default="127.0.0.1")
    receiver.add_argument("--port", type=int, default=8000)

    dispatcher = subparsers.add_parser(
        "start-dispatcher",
        help="Consume SQS y envía webhooks",
    )
    dispatcher.add_argument(
        "--queue",
        type=parse_queue_name,
        default="vulcano-events-queue",
    )
    dispatcher.add_argument(
        "--target-url",
        type=parse_webhook_url,
        required=True,
    )
    dispatcher.add_argument(
        "--secret",
        type=parse_secret_key,
        required=True,
    )
    dispatcher.add_argument(
        "--wait-time",
        type=parse_wait_time,
        default=10,
    )
    dispatcher.add_argument(
        "--endpoint",
        default="http://localhost:4566",
    )

    return parser


async def dispatch_webhook(
    target_url: str,
    secret: str,
    payload_dict: dict,
) -> None:
    """Firma el cuerpo JSON y lo envía mediante HTTP POST."""

    timestamp = int(time.time())
    payload_bytes = json.dumps(
        payload_dict,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    signature = generate_signature(
        secret,
        timestamp,
        payload_bytes,
    )
    signature_header = f"t={timestamp},v1={signature}"

    def send_request():
        return requests.post(
            target_url,
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": signature_header,
            },
            timeout=5,
        )

    try:
        response = await asyncio.to_thread(send_request)
        response.raise_for_status()

    except requests.RequestException as exc:
        error = WebhookDeliveryError(
            f"No se pudo entregar el webhook a {target_url}"
        )
        error.add_note(str(exc))
        raise error from exc


async def produce_sqs(args, logger) -> None:
    """Publica un evento en la cola configurada."""

    
    try:
        message = args.message

        if message.startswith("@"):
            with open(
                message[1:],
                "r",
                encoding="utf-8-sig",
            ) as file:
                message = file.read()

        event_data = json.loads(message)

    except json.JSONDecodeError as exc:
        raise ValueError(
            "El mensaje debe ser JSON válido."
        ) from exc

    except OSError as exc:
        raise ValueError(
            f"No se pudo leer el archivo del evento: {exc}"
        ) from exc


    if not isinstance(event_data, dict):
        raise ValueError("El evento JSON debe ser un objeto.")

    client = get_sqs_client(args.endpoint)
    queue_url = client.get_queue_url(
        QueueName=args.queue
    )["QueueUrl"]

    message_id = send_event(
        client,
        queue_url,
        event_data,
    )

    logger.info(
        "Evento publicado en SQS",
        extra={
            "MessageId": message_id,
            "QueueName": args.queue,
        },
    )
    print(f"Evento publicado. MessageId: {message_id}")



async def start_dispatcher(args, logger) -> None:
    """Consume eventos y los entrega al destino HTTP."""

    client = get_sqs_client(args.endpoint)

    queue_url = client.get_queue_url(
        QueueName=args.queue
    )["QueueUrl"]

    logger.info(
        "Despachador iniciado",
        extra={"QueueName": args.queue},
    )
    
    while True:
        messages = await asyncio.to_thread(
            receive_events,
            client,
            queue_url,
            args.wait_time,
        )

        for message in messages:
            receipt_handle = message.get("ReceiptHandle")
            message_id = message.get("MessageId", "")

            try:
                event_data = json.loads(message["Body"])

                if not isinstance(event_data, dict):
                    raise ValueError(
                        "El cuerpo del mensaje debe ser un objeto JSON."
                    )

                await dispatch_webhook(
                    args.target_url,
                    args.secret,
                    event_data,
                )

                client.delete_message(
                    QueueUrl=queue_url,
                    ReceiptHandle=receipt_handle,
                )

                logger.info(
                    "Webhook entregado correctamente",
                    extra={"MessageId": message_id},
                )

            except Exception:
                logger.exception(
                    "No se pudo procesar el mensaje SQS",
                    extra={"MessageId": message_id},
                )
                # No se elimina el mensaje: podrá volver a entregarse.
                # La DLQ requiere una redrive policy configurada en SQS.




async def start_receiver(args, logger) -> None:
    """Inicia el servidor receptor de webhooks."""

    logger.info(
        "Iniciando servidor receptor",
        extra={"Host": args.host, "Port": args.port},
    )

    config = uvicorn.Config(
        "src.vulcano_telemetry.webhook_receiver:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )

    server = uvicorn.Server(config)
    await server.serve()


async def run_command(args, logger) -> None:
    """Ejecuta el subcomando seleccionado."""

    if args.command == "produce-sqs":
        await produce_sqs(args, logger)

    elif args.command == "start-dispatcher":
        await start_dispatcher(args, logger)

    elif args.command == "start-receiver":
        await start_receiver(args, logger)


def main() -> int:
    """Punto de entrada y cierre ordenado del logging."""

    parser = build_parser()
    args = parser.parse_args()

    logging_engine = LoggingEngine()
    logger = logging_engine.start()

    try:
        asyncio.run(run_command(args, logger))
        return 0

    except NotImplementedError as exc:
        logger.error("Funcionalidad pendiente: %s", exc)
        parser.exit(2, f"Pendiente: {exc}\n")

    except SQSConnectionError:
        logger.exception("Error de conexión con SQS")
        return 1

    
    except ExceptionGroup as group:
        try:
            raise group
        except* WebhookSignatureError as errors:
            logger.error(
                "Se detectó una firma inválida",
                extra={"ErrorCount": len(errors.exceptions)},
            )
        except* WebhookTimestampError as errors:
            logger.error(
                "Se detectó un timestamp inválido",
                extra={"ErrorCount": len(errors.exceptions)},
            )
        except* SQSConnectionError as errors:
            logger.error(
                "Se detectó un fallo de SQS",
                extra={"ErrorCount": len(errors.exceptions)},
            )
        except* Exception as errors:
            logger.error(
                "Se detectaron errores no clasificados",
                extra={"ErrorCount": len(errors.exceptions)},
            )
        return 1

    except Exception:
        logger.exception("Error durante la ejecución")
        return 1


    finally:
        logging_engine.stop()


if __name__ == "__main__":
    raise SystemExit(main())
