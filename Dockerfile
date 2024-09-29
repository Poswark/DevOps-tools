FROM python:3.11-slim

ENV TZ=America/Bogota
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    curl \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

COPY . /app
WORKDIR /app

RUN pip install --no-cache-dir -r requirements.txt
RUN pip install pytest coverage
RUN coverage run -m pytest

RUN useradd -m appuser
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

ENTRYPOINT ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--workers", "4", "--bind", "0.0.0.0:8080", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1