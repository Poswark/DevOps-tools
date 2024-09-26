from flask import Flask, request, jsonify
import socket, os

app = Flask(__name__)

#configmap
URL = os.getenv("URL")  
#secreto
API_KEY = os.getenv("API_KEY")

def check_connection(host, port, timeout=10):
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
    api_key = request.headers.get('x-api-key')
    if api_key != API_KEY:
        return jsonify({'error': 'API key inválida'}), 403

    data = request.json
    host = data.get('host')
    port = data.get('port')
    
    if not host or not isinstance(port, int):
        return jsonify({'error': 'Host y puerto son requeridos y el puerto debe ser un entero'}), 400
    
    connection_status = check_connection(host, port)
    
    if connection_status:
        return jsonify({'message': f'Conexion exitosa a {host} en el puerto {port}'}), 200
    else:
        return jsonify({'message': f'Error al conectar a {host} por el puerto {port}', 'Documentacion': URL }), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)