from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
import socket
import os
import logging

log_format = "%(asctime)s - %(levelname)s - %(module)s - %(lineno)d - %(message)s"
date_format = "%Y-%m-%d %H:%M:%S"
logging.basicConfig(format=log_format, datefmt=date_format, level=logging.INFO)

URL = os.getenv("URL")
app = FastAPI()

class NsLookupRequest(BaseModel):
    host: str

class ConnectionRequest(BaseModel):
    host: str
    port: int

def check_socket_connection(host: str, port: int) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((host, port))
        logging.info(f"Conexión exitosa a {host}:{port}")
        return True
    except socket.error as e:
        logging.error(f"Error al conectar a {host}:{port}: {e}")
        return False
    finally:
        sock.close()

def get_api_key(x_api_key: str = Header(...)):
    api_key = os.getenv("API_KEY")
    if x_api_key != api_key:
        logging.warning(f"Intento de acceso con API key inválida: {x_api_key}")
        raise HTTPException(status_code=401, detail="API key inválida")
    return x_api_key

@app.post("/check-connection")
async def check_connection(request: ConnectionRequest, api_key: str = Depends(get_api_key)):
    logging.info(f"Recibida solicitud de conexión para {request.host}:{request.port}")
    connection_status = check_socket_connection(request.host, request.port)
    
    if connection_status:
        return {"message": f"Conexión exitosa a {request.host} en el puerto {request.port}"}
    else:
        error_message = (f"Error al conectar a {request.host} por el puerto {request.port}. "
                         f"Por favor, revisar la documentación: {URL}")
        logging.error(error_message)
        raise HTTPException(status_code=408, detail=error_message)

@app.get("/health")
async def health():
    logging.info("Health check ejecutado correctamente")
    return {"status": "healthy"}

@app.post("/check-nslookup")
async def check_nslookup(request: NsLookupRequest, api_key: str = Depends(get_api_key)):
    logging.info(f"Realizando nslookup para {request.host}")
    try:
        ip_address = socket.gethostbyname(request.host)
        logging.info(f"NSLookup exitoso: {request.host} resuelto a {ip_address}")
        return {"host": request.host, "ip_address": ip_address}
    except socket.gaierror as e:
        error_message = f"No se pudo resolver el dominio: {request.host}"
        logging.error(f"{error_message} - Error: {e}")
        raise HTTPException(status_code=404, detail=error_message)