import os
import pytest
import socket
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app, check_socket_connection

client = TestClient(app)  # This line should remain as is


@pytest.fixture
def test_client(monkeypatch):
    monkeypatch.setenv("API_KEY", "S3CR3T-KEY")
    return client

@pytest.fixture
def test_url(monkeypatch):
    url = "http://localhost:8000" 
    monkeypatch.setenv("URL", url)
    return url

@patch('socket.socket')
def test_check_socket_connection_success(mock_socket):
    mock_sock = mock_socket.return_value
    mock_sock.connect.return_value = None
    assert check_socket_connection("localhost", 8080) == True

@patch('socket.socket')
def test_check_socket_connection_fail(mock_socket):
    """Prueba que check_socket_connection devuelve False cuando ocurre un error de conexión"""
    mock_sock = mock_socket.return_value
    mock_sock.connect.side_effect = socket.error
    assert check_socket_connection("localhost", 8080) == False

@patch('socket.gethostbyname')
def test_check_nslookup_success(mock_gethostbyname, test_client):  # Use test_client here
    mock_gethostbyname.return_value = '127.0.0.1'
    response = client.post("/check-nslookup", json={"host": "localhost"}, headers={"x-api-key": "S3CR3T-KEY"})
    assert response.status_code == 200
    assert response.json() == {"host": "localhost", "ip_address": "127.0.0.1"}

@patch('socket.gethostbyname')
def test_check_nslookup_fail(mock_gethostbyname, test_client):
    """Prueba que la ruta /check-nslookup devuelve 404 cuando no puede resolver el dominio"""
    mock_gethostbyname.side_effect = socket.gaierror
    response = client.post("/check-nslookup", json={"host": "nonexistent-host"}, headers={"x-api-key": "S3CR3T-KEY"})
    assert response.status_code == 404
    assert response.json()["detail"] == "No se pudo resolver el dominio: nonexistent-host"

@patch('app.main.check_socket_connection')
def test_check_connection_success(mock_check_socket_connection, test_client):
    """Prueba que la ruta /check-connection devuelve éxito cuando la conexión al socket es exitosa"""
    mock_check_socket_connection.return_value = True
    response = client.post("/check-connection", json={"host": "localhost", "port": 8080}, headers={"x-api-key": "S3CR3T-KEY"})
    assert response.status_code == 200
    assert response.json() == {"message": "Conexión exitosa a localhost en el puerto 8080"}

@patch('app.main.check_socket_connection')
def test_check_connection_fail(mock_check_socket_connection, test_client, test_url):
    """Prueba que la ruta /check-connection devuelve error cuando no se puede conectar al socket"""
    mock_check_socket_connection.return_value = False
    response = test_client.post(
        "/check-connection", 
        json={"host": "localhost", "port": 8080}, 
        headers={"x-api-key": "S3CR3T-KEY"}
    )
    assert response.status_code == 408
    assert response.json() == {"detail": f"Error al conectar a localhost por el puerto 8080. Por favor, revisar la documentación: None"} 


def test_health():
    """Prueba que la ruta /health devuelve estado healthy"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_invalid_api_key():
    """Prueba que se devuelve 401 cuando la API key es inválida"""
    response = client.post("/check-connection", json={"host": "localhost", "port": 8080}, headers={"x-api-key": "INVALID-KEY"})
    assert response.status_code == 401
    assert response.json()["detail"] == "API key inválida"


