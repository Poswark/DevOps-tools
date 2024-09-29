
1. Worker Class

	•	Definición: Define el tipo de worker que Gunicorn utilizará.
	•	Opciones Comunes:
	•	sync: El valor por defecto, adecuado para aplicaciones con operaciones de E/S limitadas.
	•	gevent: Basado en corrutinas, útil para aplicaciones con muchas operaciones de E/S concurrentes.
	•	uvicorn.workers.UvicornWorker: Si utilizas ASGI en lugar de WSGI.

docker run  -d -p 8080:8080  --env API_KEY=key --env URL=http://localhost --name link-connection link-connection:1.0.4