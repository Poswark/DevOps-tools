import pytest
from flask import json
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_invalid_api_key(client):
    """Prueba cuando la API key es inválida."""
    response = client.post('/check-connection',
                           json={'host': 'example.com', 'port': 80},
                           headers={'x-api-key': 'INVALID-KEY'})
    assert response.status_code == 403
    data = json.loads(response.data)
    assert data['error'] == 'API key inválida'

def test_missing_host_or_port(client):
    """Prueba cuando faltan el host o el puerto, o el puerto no es un entero."""
    # Falta el host
    response = client.post('/check-connection',
                           json={'port': 80},
                           headers={'x-api-key': 'S3CR3T-KEY'})
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data['error'] == 'Host y puerto son requeridos y el puerto debe ser un entero'

    # Falta el puerto
    response = client.post('/check-connection',
                           json={'host': 'example.com'},
                           headers={'x-api-key': 'S3CR3T-KEY'})
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data['error'] == 'Host y puerto son requeridos y el puerto debe ser un entero'

    # Puerto no es un entero
    response = client.post('/check-connection',
                           json={'host': 'example.com', 'port': 'not-an-int'},
                           headers={'x-api-key': 'S3CR3T-KEY'})
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data['error'] == 'Host y puerto son requeridos y el puerto debe ser un entero'

def test_successful_connection(mocker, client):
    """Prueba cuando la conexión es exitosa."""
    # Mockear el resultado de check_connection
    mocker.patch('app.check_connection', return_value=True)

    response = client.post('/check-connection',
                           json={'host': 'example.com', 'port': 80},
                           headers={'x-api-key': 'S3CR3T-KEY'})
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['message'] == 'Conexion exitosa a example.com en el puerto 80'

def test_failed_connection(mocker, client):
    """Prueba cuando la conexión falla."""
    # Mockear el resultado de check_connection
    mocker.patch('app.check_connection', return_value=False)

    response = client.post('/check-connection',
                           json={'host': 'example.com', 'port': 80},
                           headers={'x-api-key': 'S3CR3T-KEY'})
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data['message'] == 'Error al conectar a example.com por el puerto 80'
    assert 'Documentacion' in data