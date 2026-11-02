# Vulcano Pay – Motor de Eventos

**TP-2: Sistema de Procesamiento de Eventos, Webhooks HMAC y Observabilidad Asíncrona con Boto3 y LocalStack**

## Descripción del proyecto

Vulcano Pay es un sistema de procesamiento de eventos desarrollado en Python que permite publicar, recibir y procesar mensajes mediante colas de Amazon SQS, utilizando LocalStack como entorno de simulación local de servicios AWS.

El sistema incorpora el envío de webhooks HTTP con autenticación mediante firmas HMAC, validación de mensajes, manejo de excepciones y un sistema de logging asíncrono con registros estructurados en formato JSON.

## Objetivos

- Implementar un sistema de publicación y procesamiento de eventos.
- Integrar Amazon SQS mediante Boto3 y LocalStack.
- Enviar webhooks HTTP con firmas HMAC.
- Validar la autenticidad e integridad de los mensajes.
- Implementar protección contra ataques de repetición (Replay Attacks).
- Gestionar errores mediante excepciones personalizadas.
- Incorporar observabilidad mediante logging asíncrono.
- Implementar pruebas automatizadas para verificar el funcionamiento del sistema.

## Tecnologías utilizadas

| Tecnología | Función |
|---|---|
| Python 3.14 | Lenguaje de programación |
| Boto3 | Comunicación con servicios AWS |
| LocalStack | Simulación local de servicios AWS |
| Amazon SQS | Gestión de colas de mensajes |
| FastAPI | Servidor receptor HTTP |
| Uvicorn | Servidor ASGI |
| Requests | Envío de peticiones HTTP |
| HMAC | Firma y autenticación de mensajes |
| Asyncio | Ejecución asíncrona |
| Pytest | Pruebas automatizadas |
| Docker | Ejecución del entorno LocalStack |

## Arquitectura del proyecto

El sistema está organizado en los siguientes componentes:

- **core_sqs.py:** gestiona las operaciones de conexión, publicación y recepción de mensajes en SQS.
- **webhook_receiver.py:** implementa el servidor receptor de webhooks.
- **webhook_crypto.py:** contiene la lógica de generación y verificación de firmas HMAC.
- **sanitizer.py:** valida y sanitiza los datos de entrada.
- **exceptions.py:** define las excepciones personalizadas del sistema.
- **logging_engine.py:** implementa el sistema de logging asíncrono y la rotación de archivos.
- **app_operator.py:** coordina la aplicación, los comandos CLI y el despachador de webhooks.

## Funcionamiento general

El flujo principal del sistema es el siguiente:

1. El usuario ejecuta un comando desde la interfaz CLI.
2. El evento se valida y se publica en una cola SQS.
3. El despachador consume los mensajes de la cola.
4. Se genera una firma HMAC para el contenido del evento.
5. El evento se envía mediante una petición HTTP POST.
6. Si la entrega es exitosa, el mensaje se elimina de la cola.
7. Si ocurre un error, se registra la excepción y el mensaje puede volver a procesarse según la configuración de SQS.

El sistema receptor permite recibir webhooks y procesar los eventos entrantes.

## Requisitos previos

Para ejecutar el proyecto se necesita:

- Python 3.14 o compatible.
- Docker Desktop.
- LocalStack en ejecución.
- Git.
- Las dependencias definidas en `requirements.txt`.

## Instalación

Clonar el repositorio:

```bash
git clone https://github.com/SantiS156/vulcano_engine.git
```

Ingresar al directorio:

```bash
cd vulcano_engine
```

Crear un entorno virtual:

```bash
python -m venv venv
```

Activar el entorno virtual en Windows:

```powershell
.\venv\Scripts\Activate.ps1
```

Instalar las dependencias:

```bash
pip install -r requirements.txt
```

## Configuración de LocalStack

Iniciar Docker Desktop y ejecutar el contenedor de LocalStack con el puerto 4566 disponible.

Comprobar su estado:

```bash
curl http://localhost:4566/_localstack/health
```

El servicio SQS debe encontrarse disponible.

La cola utilizada por defecto es:

```text
vulcano-events-queue
```

La cola debe existir previamente en LocalStack. Para las pruebas de redirección a DLQ también se utiliza una configuración de redrive policy.

## Ejecución de la aplicación

### 1. Publicar un evento en SQS

```bash
python -m src.vulcano_telemetry.app_operator produce-sqs --message "{\"evento\":\"pago_aprobado\"}"
```

También se puede publicar un evento desde un archivo JSON utilizando `@` seguido de su ruta.

### 2. Iniciar el servidor receptor

```bash
python -m src.vulcano_telemetry.app_operator start-receiver
```

Por defecto utiliza:

- Host: `127.0.0.1`
- Puerto: `8000`

### 3. Iniciar el despachador de webhooks

```bash
python -m src.vulcano_telemetry.app_operator start-dispatcher --target-url "http://127.0.0.1:8000/webhook" --secret "CAMBIAR_POR_UN_SECRETO"
```

El despachador consume los mensajes de SQS y los envía al destino configurado.

**Importante:** los comandos deben ejecutarse desde la raíz del repositorio. La cola debe estar creada y el destino HTTP debe estar disponible para recibir los webhooks.

## Sistema de seguridad

El proyecto incorpora mecanismos de seguridad:

- Firmas HMAC para verificar la autenticidad de los mensajes.
- Marca de tiempo (timestamp) para validar la antigüedad de los mensajes.
- Protección contra ataques de repetición.
- Sanitización de argumentos y validación de datos.
- Excepciones personalizadas para identificar errores específicos.

## Observabilidad y logging

El sistema utiliza un motor de logging asíncrono que permite registrar los eventos sin bloquear el procesamiento principal.

Entre sus características se encuentran:

- Registros estructurados en formato JSON.
- Identificación de eventos mediante identificadores.
- Registro de excepciones y trazas.
- Procesamiento mediante QueueHandler y QueueListener.
- Rotación automática de archivos de registro.
- Compresión de archivos antiguos mediante GZIP.

## Pruebas automatizadas

Para ejecutar las pruebas del proyecto:

```bash
python -m pytest -v
```

Las pruebas verifican:

- Rechazo de firmas inválidas.
- Protección contra timestamps vencidos y ataques de repetición.
- Redirección de mensajes fallidos a una Dead Letter Queue (DLQ).
- Estructura de los registros JSON.
- Rotación y descompresión de archivos de logging.

## Resultados de las pruebas

En la última ejecución realizada durante el desarrollo del proyecto se obtuvieron los siguientes resultados:

- 5 pruebas superadas.
- 0 pruebas fallidas.

## Integración y trabajo colaborativo

El proyecto fue desarrollado de manera colaborativa, distribuyendo las responsabilidades entre los integrantes del equipo.

Cada integrante trabajó sobre componentes específicos del sistema, que posteriormente fueron integrados en el repositorio principal.

## Repositorio

[GitHub – Vulcano Engine](https://github.com/SantiS156/vulcano_engine)

---

**Proyecto académico – TP-2**

Sistema de Procesamiento de Eventos, Webhooks HMAC y Observabilidad Asíncrona con Boto3 y LocalStack.

**Proyecto: Vulcano Pay**