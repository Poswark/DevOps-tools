import pytest
from unittest.mock import patch
from app import app

@pytest.fixture
def client():
    app.testing = True
    return app.test_client()

@patch('os.getenv')
def test_check_connection_success(mock_getenv, client):
    # Simulamos las variables de entorno
    mock_getenv.side_effect = lambda key: 'S3CR3T-KEY' if key == 'API_KEY' else 'http://localhost:2020'

    # Simulamos una solicitud POST exitosa
    response = client.post('/check-connection', json={'host': 'localhost', 'port': 8080},
                           headers={'x-api-key': 'S3CR3T-KEY'})
    
    assert response.status_code == 200
    assert b'Conexion exitosa' in response.data

@patch('os.getenv')
def test_check_connection_invalid_api_key(mock_getenv, client):
    mock_getenv.side_effect = lambda key: 'S3CR3T-KEY' if key == 'API_KEY' else 'http://localhost:2020'

    # Enviamos una API key inválida
    response = client.post('/check-connection', json={'host': 'localhost', 'port': 8080},
                           headers={'x-api-key': 'INVALID-KEY'})
    
    assert response.status_code == 403
    assert b'API key inv\xc3\xa1lida' in response.data

@patch('os.getenv')
def test_check_connection_invalid_host_port(mock_getenv, client):
    mock_getenv.side_effect = lambda key: 'S3CR3T-KEY' if key == 'API_KEY' else 'http://localhost:2020'

    # Enviamos un puerto no válido (string en vez de entero)
    response = client.post('/check-connection', json={'host': 'localhost', 'port': 'invalid-port'},
                           headers={'x-api-key': 'S3CR3T-KEY'})
    
    assert response.status_code == 400
    assert b'Host y puerto son requeridos y el puerto debe ser un entero' in response.data

@patch('os.getenv')
def test_check_connection_fail(mock_getenv, client):
    mock_getenv.side_effect = lambda key: 'S3CR3T-KEY' if key == 'API_KEY' else 'http://localhost:2020'

    # Simulamos una solicitud POST con una conexión fallida
    response = client.post('/check-connection', json={'host': 'invalid-host', 'port': 8080},
                           headers={'x-api-key': 'S3CR3T-KEY'})
    
    assert response.status_code == 400
    assert b'Error al conectar' in response.data