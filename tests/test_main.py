"""Pruebas unitarias para main.py (Atlas - DevOps Tools)."""
import base64
import logging
import socket
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import (
    HealthCheckFilter,
    _float,
    app,
    dns_check,
    http_check,
    tcp_check,
    tls_check,
)

client = TestClient(app)


# ---------------------------------------------------------------- helpers
def test_float_valid():
    assert _float("3.5", 1) == 3.5


def test_float_invalid_usa_default():
    assert _float("no-numero", 5) == 5
    assert _float(None, 7) == 7


# ---------------------------------------------------------------- tcp_check
@patch("main.socket.create_connection")
def test_tcp_check_success(mock_conn):
    mock_conn.return_value.__enter__.return_value = MagicMock()
    ok, msg = tcp_check("example.com", 443, 1)
    assert ok is True
    assert "Conexion TCP exitosa" in msg
    mock_conn.assert_called_once_with(("example.com", 443), timeout=1)


@patch("main.socket.create_connection", side_effect=socket.timeout("timed out"))
def test_tcp_check_failure(mock_conn):
    ok, msg = tcp_check("example.com", 9999, 1)
    assert ok is False
    assert "No fue posible conectar" in msg


def test_tcp_check_puerto_invalido():
    ok, msg = tcp_check("example.com", "no-es-un-puerto", 1)
    assert ok is False
    assert "No fue posible conectar" in msg


# ---------------------------------------------------------------- dns_check
@patch("main.socket.getaddrinfo")
def test_dns_check_success(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 0))]
    ok, msg = dns_check("example.com")
    assert ok is True
    assert "93.184.216.34" in msg


@patch("main.socket.getaddrinfo", side_effect=socket.gaierror("no resuelve"))
def test_dns_check_failure(mock_getaddrinfo):
    ok, msg = dns_check("dominio-que-no-existe.invalid")
    assert ok is False
    assert "No resuelve" in msg


# ---------------------------------------------------------------- http_check
@patch("main.httpx.Client")
def test_http_check_success_agrega_https(mock_client_cls):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.reason_phrase = "OK"
    mock_response.headers.items.return_value = [("Content-Type", "text/plain")]
    mock_response.url = "https://example.com/"
    mock_response.text = "hola"

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.request.return_value = mock_response
    mock_client_cls.return_value = mock_client

    ok, detail = http_check("example.com")

    assert ok is True
    assert "HTTP 200 OK" in detail
    mock_client.request.assert_called_once_with("GET", "https://example.com")


@patch("main.httpx.Client")
def test_http_check_status_error_no_es_ok(mock_client_cls):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.reason_phrase = "Internal Server Error"
    mock_response.headers.items.return_value = []
    mock_response.url = "https://example.com/"
    mock_response.text = ""

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.request.return_value = mock_response
    mock_client_cls.return_value = mock_client

    ok, detail = http_check("https://example.com")
    assert ok is False
    assert "HTTP 500" in detail


@patch("main.httpx.Client", side_effect=Exception("conexion rechazada"))
def test_http_check_excepcion(mock_client_cls):
    ok, detail = http_check("https://caida.example.com")
    assert ok is False
    assert "Error en la peticion" in detail


# ---------------------------------------------------------------- tls_check
def _mock_cert():
    return {
        "subject": ((("commonName", "example.com"),),),
        "issuer": ((("commonName", "R3"),), (("organizationName", "Let's Encrypt"),)),
        "notBefore": "Jan 1 00:00:00 2026 GMT",
        "notAfter": "Apr 1 00:00:00 2026 GMT",
        "subjectAltName": (("DNS", "example.com"), ("DNS", "www.example.com")),
    }


@patch("main.ssl.create_default_context")
@patch("main.socket.create_connection")
def test_tls_check_success(mock_conn, mock_ctx_factory):
    mock_ssock = MagicMock()
    mock_ssock.__enter__.return_value = mock_ssock
    mock_ssock.getpeercert.return_value = _mock_cert()
    mock_ssock.version.return_value = "TLSv1.3"
    mock_ssock.cipher.return_value = ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)

    mock_sock = MagicMock()
    mock_sock.__enter__.return_value = mock_sock
    mock_conn.return_value = mock_sock

    mock_ctx = MagicMock()
    mock_ctx.wrap_socket.return_value = mock_ssock
    mock_ctx_factory.return_value = mock_ctx

    ok, detail = tls_check("example.com")
    assert ok is True
    assert "Let's Encrypt" in detail
    assert "TLSv1.3" in detail


@patch("main.socket.create_connection", side_effect=OSError("conexion rechazada"))
def test_tls_check_failure(mock_conn):
    ok, detail = tls_check("example.com")
    assert ok is False
    assert "Error TLS" in detail


# ---------------------------------------------------------------- HealthCheckFilter
def test_health_check_filter_oculta_health():
    record = logging.makeLogRecord({"msg": '127.0.0.1 - "GET /health HTTP/1.1" 200'})
    assert HealthCheckFilter().filter(record) is False


def test_health_check_filter_deja_pasar_otras_rutas():
    record = logging.makeLogRecord({"msg": '127.0.0.1 - "GET /connection HTTP/1.1" 200'})
    assert HealthCheckFilter().filter(record) is True


# ---------------------------------------------------------------- rutas
def test_health_endpoint():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy"}


def test_index_ok():
    r = client.get("/")
    assert r.status_code == 200
    assert "DevOps Tools" in r.text
    assert "Atlas" in r.text


@pytest.mark.parametrize("path", ["/connection", "/base64", "/cert"])
def test_paginas_get_ok(path):
    r = client.get(path)
    assert r.status_code == 200


@patch("main.tcp_check", return_value=(True, "Conexion TCP exitosa a x:1 (1 ms)"))
def test_connection_post_tcp_ok(mock_tcp):
    r = client.post("/connection", data={"check": "tcp", "host": "x", "port": "1"})
    assert r.status_code == 200
    assert "OK" in r.text
    mock_tcp.assert_called_once()


@patch("main.dns_check", return_value=(False, "No resuelve x -> error"))
def test_connection_post_dns_fail(mock_dns):
    r = client.post("/connection", data={"check": "dns", "host": "x"})
    assert r.status_code == 200
    assert "FALLO" in r.text


@patch("main.tls_check", return_value=(True, "Protocolo: TLSv1.3"))
def test_connection_post_tls_ok(mock_tls):
    r = client.post("/connection", data={"check": "tls", "host": "x", "port": "443"})
    assert r.status_code == 200
    assert "OK" in r.text


@patch("main.http_check", return_value=(True, "HTTP 200 OK"))
def test_connection_post_http_ok(mock_http):
    r = client.post(
        "/connection",
        data={"check": "http", "url": "https://x", "method": "GET"},
    )
    assert r.status_code == 200
    mock_http.assert_called_once()
    # el checkbox "insecure" desmarcado -> verify=True
    assert mock_http.call_args.args[3] is True


@patch("main.tcp_check", side_effect=RuntimeError("boom"))
def test_connection_post_excepcion_inesperada(mock_tcp):
    r = client.post("/connection", data={"check": "tcp", "host": "x", "port": "1"})
    assert r.status_code == 200
    assert "Entrada invalida" in r.text


def test_base64_encode():
    r = client.post("/base64", data={"mode": "encode", "text": "hola gio"})
    assert r.status_code == 200
    assert base64.b64encode(b"hola gio").decode() in r.text


def test_base64_decode():
    encoded = base64.b64encode(b"hola gio").decode()
    r = client.post("/base64", data={"mode": "decode", "text": encoded})
    assert r.status_code == 200
    assert "hola gio" in r.text


def test_base64_decode_invalido_muestra_error():
    # "hola mundo" no es base64 valido: al filtrar espacios y agregar el
    # padding "===" queda una longitud que binascii no puede decodificar.
    r = client.post("/base64", data={"mode": "decode", "text": "hola mundo"})
    assert r.status_code == 200
    assert "No se pudo procesar" in r.text


def test_cert_sin_contenido_muestra_error():
    r = client.post("/cert", data={"cert": "", "key_name": "tls.crt"})
    assert r.status_code == 200
    assert "Pega el contenido del certificado" in r.text


def test_cert_convierte_a_una_linea():
    pem = "-----BEGIN CERTIFICATE-----\nAAAA\nBBBB\n-----END CERTIFICATE-----"
    r = client.post("/cert", data={"cert": pem, "key_name": "tls.crt"})
    assert r.status_code == 200

    normalized = "\n".join(pem.splitlines()) + "\n"
    expected_one_line = normalized.replace("\n", "\\n")
    expected_b64 = base64.b64encode(normalized.encode()).decode()

    assert expected_one_line in r.text
    assert expected_b64 in r.text
    assert "jq -n --arg cert" in r.text
    assert '"tls.crt"' in r.text
