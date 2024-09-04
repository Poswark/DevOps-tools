from flask import Flask, request, jsonify
import socket

app = Flask(__name__)

def check_connection(host, port, timeout=5):
    """
    Verifica la conexión a un host y puerto específicos.

    Args:
        host (str): La dirección del host (por ejemplo, 'www.google.com' o '192.168.1.1').
        port (int): El puerto al que deseas conectarte.
        timeout (int): Tiempo máximo en segundos para intentar la conexión.

    Returns:
        bool: True si la conexión es exitosa, False si no.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        return True
    except (socket.timeout, socket.error):
        return False
    finally:
        sock.close()

@app.route('/check-connection', methods=['POST'])
def check_connection_endpoint():
    data = request.json
    host = data.get('host')
    port = data.get('port')
    
    if not host or not isinstance(port, int):
        return jsonify({'error': 'Host y puerto son requeridos y el puerto debe ser un entero'}), 400
    
    connection_status = check_connection(host, port)
    
    if connection_status:
        return jsonify({'message': f'Conexión exitosa a {host}:{port}'}), 200
    else:
        return jsonify({'message': f'Error al conectar a {host}:{port}'}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)