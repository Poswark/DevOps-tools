import multiprocessing
import os

bind = f"0.0.0.0:{os.getenv('PORT', '8080')}"
worker_class = "uvicorn.workers.UvicornWorker"
workers = int(os.getenv("WEB_CONCURRENCY", min(multiprocessing.cpu_count() * 2 + 1, 4)))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 30
keepalive = 5

log_level = os.getenv("LOG_LEVEL", "info").upper()
log_dir = os.getenv("LOG_DIR", "logs")
os.makedirs(log_dir, exist_ok=True)

# El log de acceso completo (incluye /health) siempre se escribe a
# logs/access.log. La consola (stdout -> `docker compose logs`) omite las
# líneas de /health para no inundarse con el ping del healthcheck, pero el
# registro sigue existiendo integro en el archivo.
logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "hide_health": {"()": "main.HealthCheckFilter"},
    },
    "formatters": {
        "access": {
            "format": "%(asctime)s %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "generic": {
            "format": "%(asctime)s [%(process)d] [%(levelname)s] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console_access": {
            "class": "logging.StreamHandler",
            "formatter": "access",
            "filters": ["hide_health"],
            "stream": "ext://sys.stdout",
        },
        "file_access": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "access",
            "filename": os.path.join(log_dir, "access.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 3,
        },
        "console_error": {
            "class": "logging.StreamHandler",
            "formatter": "generic",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {
        "level": log_level,
        "handlers": ["console_error"],
    },
    "loggers": {
        "gunicorn.access": {
            "handlers": ["console_access", "file_access"],
            "level": log_level,
            "propagate": False,
        },
        "gunicorn.error": {
            "handlers": ["console_error"],
            "level": log_level,
            "propagate": False,
        },
    },
}

loglevel = log_level.lower()
