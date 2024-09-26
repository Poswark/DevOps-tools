from flask import Flask, request, jsonify
import socket, os
import pytest

from app.main import app, check_connection

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

# Mocking os.getenv to avoid errors during testing
@pytest.fixture
def mock_env_vars(monkeypatch):
    monkeypatch.setenv("URL", "https://example.com/docs")
    monkeypatch.setenv("API_KEY", "KEY-BASIC")

def test_check_connection_success(monkeypatch):
    # Mocking socket.connect to simulate a successful connection
    monkeypatch.setattr(socket.socket, "connect", lambda *args: None)
    assert check_connection("google.com", 80) == True

def test_check_connection_failure(monkeypatch):
    # Mocking socket.connect to simulate a connection failure
    with pytest.raises(Exception):
        monkeypatch.setattr(socket.socket, "connect", lambda *args: (_ for _ in ()).throw(Exception))
        check_connection("nonexistent-host.com", 80) 

def test_check_connection_endpoint_success(client, mock_env_vars):
    response = client.post('/check-connection', json={'host': 'google.com', 'port': 80}, headers={'x-api-key': 'KEY-BASIC'})
    assert response.status_code == 403

def test_check_connection_endpoint_invalid_api_key(client, mock_env_vars):
    response = client.post('/check-connection', json={'host': 'google.com', 'port': 80}, headers={'x-api-key': 'invalid_api_key'})
    assert response.status_code == 403
    assert response.json['error'] == 'API key inválida'
