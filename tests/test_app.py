import os
import pytest
import socket
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app, check_socket_connection 

client = TestClient(app)

@pytest.fixture
def get_api_key_mock():
    with patch('os.getenv') as mock_getenv:
        mock_getenv.side_effect = lambda key: 'S3CR3T-KEY' if key == 'API_KEY' else None
        yield mock_getenv

@patch('socket.socket')
def test_check_socket_connection_success(mock_socket):
    mock_sock = mock_socket.return_value
    mock_sock.connect.return_value = None
    assert check_socket_connection("localhost", 8080) == True

@patch('socket.socket')
def test_check_socket_connection_fail(mock_socket):
    # Configurar el mock para simular un error de conexión
    mock_sock = mock_socket.return_value
    mock_sock.connect.side_effect = socket.error

    # Realizar la prueba
    assert check_socket_connection("localhost", 8080) == False
