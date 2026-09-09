# DevOps Tools · Atlas

Panel interno de utilidades DevOps. FastAPI con templates Jinja2 y 4 herramientas:

1. **Connection** (`/connection`) — pruebas TCP (telnet), HTTP (curl), DNS y certificado TLS.
2. **Base64** (`/base64`) — codificar / decodificar texto.
3. **Certificados** (`/cert`) — PEM completo a una sola linea, comando `jq -n` y base64.
4. **Recursos y HPA** (`/resources`) — right-sizing de `requests`/`limits` a partir de las
   metricas de 24h de Dynatrace, mas el HPA dimensionado por transacciones por minuto.

`/health` responde el healthcheck. `main.py` esta en la raiz del proyecto y se sirve con
gunicorn usando `uvicorn.workers.UvicornWorker`.

## Recursos y HPA

Se le pegan el p95 y el maximo de CPU y memoria de las ultimas 24 horas y devuelve el
bloque `resources:` listo para el
Deployment, el manifiesto del `HorizontalPodAutoscaler`, las conversiones de unidades y
los hallazgos. Si ademas se le pasa la configuracion actual, calcula cuanto se esta
reservando de mas; si se le pasa el throughput, dimensiona el autoscaler.

### Unidades

Lo ideal es escribir la unidad (`350m`, `0.5 cores`, `650Mi`, `2Gi`, `1024M`). Para poder
pegar directo de Dynatrace, un numero suelto se interpreta asi:

| Se escribe | Se entiende | Por que |
|---|---|---|
| `350` (CPU, entero >= 10) | 350m | Dynatrace muestra la CPU en millicores |
| `2` o `0.5` (CPU, < 10) | 2 cores / 500m | nadie configura 2 millicores |
| `650` (memoria) | 650Mi | Dynatrace muestra la memoria en MiB |
| `650b` (memoria) | 650 bytes | los bytes hay que pedirlos explicitamente |

El resultado siempre abre con una tarjeta **"Se interpretaron tus datos asi"** que muestra
lo que entendio, y avisa cuando los valores parecen no tener unidad (una CPU p95 de 350
cores, por ejemplo) o cuando el maximo quedo por debajo del p95.

| Valor | Formula | Por que |
|---|---|---|
| request CPU | p95 x 1.15, redondeado a 10m | CPU es compresible: el request solo garantiza el uso habitual |
| limit CPU | max(maximo x 1.5, request x 2) | deja espacio a los picos sin caer en throttling |
| request memoria | p95 x 1.15, redondeado a 32Mi | reserva realista para el scheduler |
| limit memoria | max(maximo x 1.3, request x 1.25) | memoria es incompresible: pasarse del limit es OOMKilled |
| capacidad por pod | (request x utilizacion objetivo) / costo por TPM | el costo por TPM se deduce de `cpu_p95 / (TPM pico / replicas)` |
| minReplicas | TPM promedio / capacidad por pod, minimo 2 | dos replicas por tolerancia a fallos |
| maxReplicas | TPM objetivo (o pico x 1.5) / capacidad por pod | cubre el crecimiento planeado |

Dos advertencias que la herramienta repite porque son las que mas cuestan en produccion:
el HPA compara contra el **request** de CPU y no contra el limit (si se infla el request,
el autoscaler nunca dispara), y el limit de memoria debe cubrir el pico observado porque
pasarse mata el pod.

## Local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
gunicorn -c gunicorn.conf.py main:app        # http://localhost:8080
# o en desarrollo:
uvicorn main:app --reload --port 8080
```

## Pruebas

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python3 -m coverage run -m pytest
python3 -m coverage report -m
```

`tests/test_main.py` cubre las tres primeras cards y el filtro de logs;
`tests/test_resources.py` cubre la calculadora de recursos y el HPA. Toda la red esta
mockeada (socket, ssl, httpx), asi que la suite corre sin salir a internet.
`tests/conftest.py` agrega la raiz del repo al `sys.path` para que `import main` funcione
sin importar como se invoque pytest.

## Docker

```bash
docker compose up --build -d
docker compose logs -f
curl localhost:8080/health
```

El build de la imagen tiene dos etapas: una etapa `test` instala `requirements-dev.txt`,
copia `tests/` y corre `coverage run -m pytest`; si una prueba falla, el build se detiene
ahi y la imagen final nunca se construye. La etapa final solo instala `requirements.txt`
(sin pytest/coverage) y copia el codigo ya verificado desde la etapa `test`.

### Logs

`/health` se sigue registrando siempre en `logs/access.log` (montado por `docker-compose.yml`),
pero se filtra de la salida de consola (`docker compose logs`) para no llenarla con el ping
del healthcheck. El filtro (`HealthCheckFilter`) vive en `main.py` y se referencia desde
`gunicorn.conf.py`.

## Variables de entorno

| Variable | Default | Descripcion |
|---|---|---|
| `PORT` | 8080 | Puerto de escucha |
| `WEB_CONCURRENCY` | cpu*2+1 (max 4) | Numero de workers |
| `GUNICORN_TIMEOUT` | 60 | Timeout por request |
| `LOG_LEVEL` | info | Nivel de log |
| `LOG_DIR` | logs | Carpeta del log de acceso |

## Estructura

```
main.py              app, helpers y HealthCheckFilter
gunicorn.conf.py     workers, worker class y configuracion de logging
templates/           base.html + una plantilla por card
tests/               pytest (sin red real)
requirements.txt     dependencias de produccion
requirements-dev.txt dependencias de pruebas (incluye las de produccion)
```
docker run  -d -p 8080:8080  --env API_KEY=key --env URL=http://localhost --name link-connection link-connection:1.0.4

[![Python application](https://github.com/Poswark/link-connection-api/actions/workflows/python-app.yml/badge.svg)](https://github.com/Poswark/link-connection-api/actions/workflows/python-app.yml)
