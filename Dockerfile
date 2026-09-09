# syntax=docker/dockerfile:1

# ---------------------------------------------------------------- test
# Instala dependencias de dev (incluye las de produccion via -r) y corre la
# suite de pytest/coverage. Si una prueba falla, esta etapa falla y el build
# completo se detiene aqui: la imagen final nunca llega a construirse.
FROM python:3.12-slim AS test
WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY main.py gunicorn.conf.py ./
COPY templates ./templates
COPY tests ./tests

RUN python3 -m coverage run -m pytest \
    && python3 -m coverage report -m

# ---------------------------------------------------------------- runtime
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Se copian desde la etapa "test": si las pruebas no pasaron, estos archivos
# nunca se generan y el build ya fallo antes de llegar aqui.
COPY --from=test /app/main.py /app/gunicorn.conf.py ./
COPY --from=test /app/templates ./templates

RUN mkdir -p /app/logs \
    && useradd -m -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:${PORT}/health || exit 1

CMD ["gunicorn", "-c", "gunicorn.conf.py", "main:app"]
