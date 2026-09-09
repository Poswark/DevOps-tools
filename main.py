import base64
import json
import logging
import os
import re
import socket
import ssl
import time
from math import ceil

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(module)s - %(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger("webtools")

app = FastAPI(title="Web Tools", version="1.0.0")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


class HealthCheckFilter(logging.Filter):
    """Oculta las lineas de acceso a /health del handler al que se aplica.

    Referenciado desde gunicorn.conf.py como "main.HealthCheckFilter" en el
    handler de consola del logger de acceso. El healthcheck de Docker/Cloud
    Run golpea /health cada pocos segundos y llena la consola de ruido; este
    filtro no desactiva ese logging, solo lo saca del handler de consola. El
    handler de archivo (logs/access.log), que no usa este filtro, sigue
    recibiendo *todas* las lineas, /health incluido.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return "/health" not in record.getMessage()


# ---------------------------------------------------------------- helpers
def tcp_check(host, port, timeout=5.0):
    start = time.time()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            ms = (time.time() - start) * 1000
            return True, f"Conexion TCP exitosa a {host}:{port} ({ms:.0f} ms)"
    except Exception as e:
        return False, f"No fue posible conectar a {host}:{port} -> {e}"


def dns_check(host):
    try:
        infos = socket.getaddrinfo(host, None)
        ips = sorted({i[4][0] for i in infos})
        return True, "Resuelve a: " + ", ".join(ips)
    except Exception as e:
        return False, f"No resuelve {host} -> {e}"


def http_check(url, method="GET", timeout=10.0, verify=True):
    if not re.match(r"^https?://", url):
        url = "https://" + url
    start = time.time()
    try:
        with httpx.Client(timeout=timeout, verify=verify, follow_redirects=True) as c:
            r = c.request(method, url)
        ms = (time.time() - start) * 1000
        headers = "\n".join(f"{k}: {v}" for k, v in r.headers.items())
        detail = (f"HTTP {r.status_code} {r.reason_phrase} en {ms:.0f} ms\n"
                  f"URL final: {r.url}\n\n--- Headers ---\n{headers}\n\n"
                  f"--- Body (primeros 2000 chars) ---\n{r.text[:2000]}")
        return 200 <= r.status_code < 400, detail
    except Exception as e:
        return False, f"Error en la peticion a {url} -> {e}"


def tls_check(host, port=443, timeout=5.0):
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                subject = dict(x[0] for x in cert.get("subject", []))
                issuer = dict(x[0] for x in cert.get("issuer", []))
                sans = ", ".join(v for k, v in cert.get("subjectAltName", []) if k == "DNS")
                detail = (f"Protocolo: {ssock.version()}\n"
                          f"Cipher: {ssock.cipher()[0]}\n"
                          f"CN: {subject.get('commonName')}\n"
                          f"Emisor: {issuer.get('commonName')} ({issuer.get('organizationName')})\n"
                          f"Valido desde: {cert.get('notBefore')}\n"
                          f"Valido hasta: {cert.get('notAfter')}\n"
                          f"SAN: {sans}")
                return True, detail
    except Exception as e:
        return False, f"Error TLS con {host}:{port} -> {e}"


def _float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- helpers

MI = 1024 ** 2
GI = 1024 ** 3
CPU_STEP_M = 10           # los requests de CPU se redondean a 10m
MEM_STEP = 32 * MI        # los de memoria a 32Mi

_MEM_RE = re.compile(r"^([0-9]*\.?[0-9]+)\s*([kmgt]i?b?|b)?$")


CPU_BARE_CORES_MAX = 10   # un numero suelto menor a esto se lee como cores


def parse_cpu(text, default=None):
    """Devuelve millicores (float).

    '250m' -> 250     sufijo explicito
    '2 cores' -> 2000 sufijo explicito
    '0.5' -> 500      decimal suelto = cores
    '2' -> 2000       entero suelto < 10 = cores
    '350' -> 350      entero suelto >= 10 = millicores (asi los muestra Dynatrace)
    """
    if text is None:
        return default
    raw = str(text).strip().lower()
    explicit_cores = "core" in raw
    t = raw.replace("cores", "").replace("core", "").strip()
    if not t:
        return default
    try:
        if t.endswith("m"):
            return float(t[:-1])
        value = float(t)
    except ValueError:
        raise ValueError(f"CPU invalida: '{text}'. Usa '250m', '0.5' o '2'.")
    if explicit_cores or value < CPU_BARE_CORES_MAX:
        return value * 1000
    return value


def parse_memory(text, default=None):
    """Devuelve bytes.

    '512Mi' -> 536870912   sufijo explicito
    '2Gi', '1024M', '1.5G' -> segun su unidad
    '650' -> 681574400     numero suelto = MiB (asi lo muestra Dynatrace)
    '650b' -> 650          bytes solo si se pide explicitamente
    """
    if text is None:
        return default
    t = str(text).strip().lower().replace(" ", "")
    if not t:
        return default
    m = _MEM_RE.match(t)
    if not m:
        raise ValueError(f"Memoria invalida: '{text}'. Usa '512Mi', '2Gi' o '1024M'.")
    factors = {"b": 1, "k": 1000, "m": 10 ** 6, "g": 10 ** 9, "t": 10 ** 12,
               "ki": 1024, "mi": MI, "gi": GI, "ti": 1024 ** 4}
    sufijo = m.group(2)
    if not sufijo:
        unit = "mi"                     # numero suelto = MiB
    elif sufijo == "b":
        unit = "b"
    else:
        unit = sufijo.rstrip("b")
    return int(float(m.group(1)) * factors[unit])


def format_cpu(millicores):
    """1000 -> '1', 250 -> '250m'."""
    m = int(ceil(millicores))
    return str(m // 1000) if m >= 1000 and m % 1000 == 0 else f"{m}m"


def format_memory(nbytes):
    """1073741824 -> '1Gi', 536870912 -> '512Mi'."""
    b = int(nbytes)
    if b % GI == 0:
        return f"{b // GI}Gi"
    return f"{int(ceil(b / MI))}Mi"


def _ceil_to(value, step):
    return int(ceil(value / step) * step)


def recommend_resources(cpu_p95_m, cpu_max_m, mem_p95_b, mem_max_b):
    """Right-sizing a partir de metricas de 24h (Dynatrace).

    CPU es compresible: el request cubre el p95 con 15% de holgura y el limit
    deja espacio para picos. Memoria es incompresible (si se pasa del limit el
    pod muere por OOMKilled), asi que el limit cubre el maximo observado + 30%.
    """
    req_cpu = max(CPU_STEP_M, _ceil_to(cpu_p95_m * 1.15, CPU_STEP_M))
    lim_cpu = _ceil_to(max(cpu_max_m * 1.5, req_cpu * 2), CPU_STEP_M)
    req_mem = max(64 * MI, _ceil_to(mem_p95_b * 1.15, MEM_STEP))
    lim_mem = _ceil_to(max(mem_max_b * 1.3, req_mem * 1.25), MEM_STEP)
    return {"req_cpu": req_cpu, "lim_cpu": lim_cpu,
            "req_mem": req_mem, "lim_mem": lim_mem}


def qos_class(req_cpu, lim_cpu, req_mem, lim_mem):
    """Clase de QoS que Kubernetes le asigna al pod."""
    if req_cpu == lim_cpu and req_mem == lim_mem:
        return "Guaranteed"
    return "Burstable"


def recommend_hpa(cpu_p95_m, req_cpu_m, replicas, tpm_avg, tpm_peak,
                  target_util=70, tpm_target=None):
    """Dimensiona el HPA a partir del throughput medido.

    Deduce cuanta CPU cuesta una transaccion con las metricas actuales y
    calcula cuantas transacciones por minuto aguanta un pod al porcentaje de
    utilizacion objetivo. Ojo: el HPA mide contra el *request*, no el limit.

    maxReplicas se dimensiona contra el TPM objetivo si lo dan (planeacion de
    crecimiento); si no, contra el pico observado con 50% de margen.
    """
    if not replicas or not tpm_peak or cpu_p95_m <= 0:
        return None
    tpm_per_pod = tpm_peak / replicas
    m_per_tpm = cpu_p95_m / tpm_per_pod
    cap_per_pod = (req_cpu_m * target_util / 100) / m_per_tpm
    if cap_per_pod <= 0:
        return None
    objetivo = max(tpm_target, tpm_peak) if tpm_target else tpm_peak * 1.5
    min_r = max(2, int(ceil((tpm_avg or 0) / cap_per_pod)))
    max_r = max(min_r + 1, int(ceil(objetivo / cap_per_pod)))
    return {"min_replicas": min_r, "max_replicas": max_r,
            "target_util": int(target_util),
            "tpm_per_pod": round(cap_per_pod),
            "m_per_tpm": round(m_per_tpm, 3),
            "tpm_per_pod_actual": round(tpm_per_pod),
            "tpm_objetivo": round(objetivo)}


def resource_warnings(m, reco, hpa):
    """Lista de hallazgos: (nivel, texto). nivel = ok | warn | info."""
    out = []
    cpu_max, mem_max = m["cpu_max"], m["mem_max"]

    # cordura: casi siempre significa que se olvido la unidad
    if m["cpu_p95"] > 32000:
        out.append(("warn", f"{format_cpu(m['cpu_p95'])} de CPU p95 son "
                            f"{round(m['cpu_p95'] / 1000)} cores. Si querias millicores "
                            "escribelos con la unidad, por ejemplo '350m'."))
    if m["mem_p95"] > 128 * GI:
        out.append(("warn", f"{format_memory(m['mem_p95'])} de memoria p95 es muchisimo. "
                            "Si venia en bytes o MiB, escribe la unidad ('650Mi')."))
    if cpu_max < m["cpu_p95"]:
        out.append(("warn", "El maximo de CPU es menor que el p95: revisa que no esten "
                            "invertidos los campos."))
    if mem_max < m["mem_p95"]:
        out.append(("warn", "El maximo de memoria es menor que el p95: revisa que no esten "
                            "invertidos los campos."))

    if m.get("lim_cpu_actual") and cpu_max > m["lim_cpu_actual"] * 0.9:
        out.append(("warn", "El pico de CPU esta sobre el 90% del limit actual: "
                            "es muy probable que estes sufriendo CPU throttling."))
    if m.get("lim_mem_actual") and mem_max > m["lim_mem_actual"] * 0.9:
        out.append(("warn", "El pico de memoria esta sobre el 90% del limit actual: "
                            "riesgo real de OOMKilled. Sube el limit antes que nada."))
    if m.get("req_cpu_actual") and m["req_cpu_actual"] > m["cpu_p95"] * 2:
        veces = round(m["req_cpu_actual"] / m["cpu_p95"], 1)
        out.append(("info", f"El request de CPU actual es {veces}x el uso p95: el scheduler "
                            "esta reservando CPU que nadie usa y te cuesta densidad de nodos."))
    if m.get("req_mem_actual") and m["req_mem_actual"] > m["mem_p95"] * 2:
        out.append(("info", "El request de memoria actual duplica el uso p95: hay "
                            "espacio para densificar los nodos."))
    if mem_max > m["mem_p95"] * 2:
        out.append(("info", "El maximo de memoria duplica el p95: la app tiene picos "
                            "marcados (GC, cargas puntuales). El limit sugerido ya los cubre."))

    out.append(("ok", f"Clase de QoS resultante: "
                      f"{qos_class(reco['req_cpu'], reco['lim_cpu'], reco['req_mem'], reco['lim_mem'])}."))
    if hpa:
        out.append(("info", "El HPA escala segun el porcentaje del *request* de CPU, "
                            "no del limit. Si inflas el request, el HPA nunca dispara."))
    return out


def build_hpa_yaml(name, min_replicas, max_replicas, target_util):
    """Manifiesto del HPA. Se arma siempre: con los numeros calculados si hay
    datos de throughput, o con valores conservadores como plantilla si no."""
    return (
        "apiVersion: autoscaling/v2\n"
        "kind: HorizontalPodAutoscaler\n"
        "metadata:\n"
        f"  name: {name}\n"
        "spec:\n"
        "  scaleTargetRef:\n"
        "    apiVersion: apps/v1\n"
        "    kind: Deployment\n"
        f"    name: {name}\n"
        f"  minReplicas: {min_replicas}\n"
        f"  maxReplicas: {max_replicas}\n"
        "  metrics:\n"
        "    - type: Resource\n"
        "      resource:\n"
        "        name: cpu\n"
        "        target:\n"
        "          type: Utilization\n"
        f"          averageUtilization: {target_util}\n"
        "  behavior:\n"
        "    scaleDown:\n"
        "      stabilizationWindowSeconds: 300"
    )


def resource_savings(m, reco, replicas):
    """Diferencia entre lo reservado hoy y lo recomendado, por replica y total."""
    if not replicas or not m.get("req_cpu_actual") or not m.get("req_mem_actual"):
        return None
    d_cpu = (m["req_cpu_actual"] - reco["req_cpu"]) * replicas
    d_mem = (m["req_mem_actual"] - reco["req_mem"]) * replicas
    return {"cpu_cores": round(d_cpu / 1000, 2), "mem_gib": round(d_mem / GI, 2)}


# ---------------------------------------------------------------- routes

@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"active": "home"})


@app.get("/connection", response_class=HTMLResponse)
async def connection_form(request: Request):
    return templates.TemplateResponse(
        request, "connection.html",
        {"ok": None, "output": "", "form": {}, "active": "connection"})


@app.post("/connection", response_class=HTMLResponse)
async def connection_run(
    request: Request,
    check: str = Form("tcp"),
    host: str = Form(""),
    port: str = Form(""),
    timeout: str = Form(""),
    url: str = Form(""),
    method: str = Form("GET"),
    insecure: str = Form(""),
):
    form = {"check": check, "host": host, "port": port, "timeout": timeout,
            "url": url, "method": method, "insecure": insecure}
    host = host.strip()
    try:
        if check == "tcp":
            ok, output = tcp_check(host, port or 443, _float(timeout, 5))
        elif check == "dns":
            ok, output = dns_check(host)
        elif check == "tls":
            ok, output = tls_check(host, port or 443, _float(timeout, 5))
        else:
            ok, output = http_check(url.strip(), method,
                                    _float(timeout, 10), insecure != "on")
    except Exception as e:
        ok, output = False, f"Entrada invalida: {e}"
    log.info("check=%s ok=%s host=%s url=%s", check, ok, host, url)
    return templates.TemplateResponse(
        request, "connection.html",
        {"ok": ok, "output": output, "form": form, "active": "connection"})


@app.get("/base64", response_class=HTMLResponse)
async def b64_form(request: Request):
    return templates.TemplateResponse(
        request, "base64.html",
        {"output": "", "error": "", "form": {}, "active": "base64"})


@app.post("/base64", response_class=HTMLResponse)
async def b64_run(request: Request, mode: str = Form("encode"), text: str = Form("")):
    output, error = "", ""
    try:
        if mode == "decode":
            output = base64.b64decode("".join(text.split()) + "===").decode("utf-8", "replace")
        else:
            output = base64.b64encode(text.encode()).decode()
    except Exception as e:
        error = f"No se pudo procesar: {e}"
    return templates.TemplateResponse(
        request, "base64.html",
        {"output": output, "error": error, "form": {"mode": mode, "text": text},
         "active": "base64"})


@app.get("/cert", response_class=HTMLResponse)
async def cert_form(request: Request):
    return templates.TemplateResponse(
        request, "cert.html",
        {"one_line": "", "jq_cmd": "", "b64": "", "error": "", "form": {}, "active": "cert"})


@app.post("/cert", response_class=HTMLResponse)
async def cert_run(request: Request, cert: str = Form(""), key_name: str = Form("tls.crt")):
    ctx = {"one_line": "", "jq_cmd": "", "b64": "", "error": "",
           "form": {"cert": cert, "key_name": key_name}, "active": "cert"}
    pem = cert.strip()
    key = (key_name or "tls.crt").strip()
    if not pem:
        ctx["error"] = "Pega el contenido del certificado."
    else:
        normalized = "\n".join(l.rstrip() for l in pem.splitlines() if l.strip()) + "\n"
        ctx["one_line"] = normalized.replace("\n", "\\n")
        ctx["b64"] = base64.b64encode(normalized.encode()).decode()
        ctx["jq_cmd"] = "jq -n --arg cert %s '{%s: $cert}'" % (
            json.dumps(normalized), json.dumps(key))
    return templates.TemplateResponse(request, "cert.html", ctx)


# ---------------------------------------------------------------- routes

@app.get("/resources", response_class=HTMLResponse)
async def resources_form(request: Request):
    return templates.TemplateResponse(
        request, "resources.html",
        {"result": None, "error": "", "form": {}, "active": "resources"})


@app.post("/resources", response_class=HTMLResponse)
async def resources_run(
    request: Request,
    cpu_p95: str = Form(""),
    cpu_max: str = Form(""),
    mem_p95: str = Form(""),
    mem_max: str = Form(""),
    replicas: str = Form("1"),
    req_cpu_actual: str = Form(""),
    lim_cpu_actual: str = Form(""),
    req_mem_actual: str = Form(""),
    lim_mem_actual: str = Form(""),
    tpm_avg: str = Form(""),
    tpm_peak: str = Form(""),
    tpm_target: str = Form(""),
    target_util: str = Form("70"),
    workload: str = Form("mi-servicio"),
):
    form = {"cpu_p95": cpu_p95, "cpu_max": cpu_max, "mem_p95": mem_p95,
            "mem_max": mem_max, "replicas": replicas, "req_cpu_actual": req_cpu_actual,
            "lim_cpu_actual": lim_cpu_actual, "req_mem_actual": req_mem_actual,
            "lim_mem_actual": lim_mem_actual, "tpm_avg": tpm_avg,
            "tpm_peak": tpm_peak, "tpm_target": tpm_target,
            "target_util": target_util, "workload": workload}
    ctx = {"result": None, "error": "", "form": form, "active": "resources"}

    try:
        m = {
            "cpu_p95": parse_cpu(cpu_p95),
            "cpu_max": parse_cpu(cpu_max),
            "mem_p95": parse_memory(mem_p95),
            "mem_max": parse_memory(mem_max),
            "req_cpu_actual": parse_cpu(req_cpu_actual),
            "lim_cpu_actual": parse_cpu(lim_cpu_actual),
            "req_mem_actual": parse_memory(req_mem_actual),
            "lim_mem_actual": parse_memory(lim_mem_actual),
        }
        if m["cpu_p95"] is None or m["mem_p95"] is None:
            raise ValueError("El p95 de CPU y el de memoria son obligatorios.")
        m["cpu_max"] = m["cpu_max"] or m["cpu_p95"]
        m["mem_max"] = m["mem_max"] or m["mem_p95"]
        n_replicas = int(replicas or 1)
        util = _float(target_util, 70) or 70
        t_avg = _float(tpm_avg, 0)
        t_peak = _float(tpm_peak, 0)
        t_target = _float(tpm_target, 0)
    except (ValueError, TypeError) as e:
        ctx["error"] = str(e)
        return templates.TemplateResponse(request, "resources.html", ctx)

    reco = recommend_resources(m["cpu_p95"], m["cpu_max"], m["mem_p95"], m["mem_max"])
    hpa = recommend_hpa(m["cpu_p95"], reco["req_cpu"], n_replicas,
                        t_avg, t_peak, util, t_target)

    name = (workload or "mi-servicio").strip() or "mi-servicio"
    resources_yaml = (
        "resources:\n"
        f"  requests:\n"
        f"    cpu: {format_cpu(reco['req_cpu'])}\n"
        f"    memory: {format_memory(reco['req_mem'])}\n"
        f"  limits:\n"
        f"    cpu: {format_cpu(reco['lim_cpu'])}\n"
        f"    memory: {format_memory(reco['lim_mem'])}"
    )
    if hpa:
        hpa_yaml = build_hpa_yaml(name, hpa["min_replicas"],
                                  hpa["max_replicas"], hpa["target_util"])
    else:
        # sin datos de throughput no se puede dimensionar, pero el manifiesto
        # se muestra igual como plantilla lista para ajustar a mano
        hpa_yaml = build_hpa_yaml(name, 2, 4, int(util))

    ctx["result"] = {
        "reco": reco,
        "hpa": hpa,
        "hpa_es_plantilla": hpa is None,
        "resources_yaml": resources_yaml,
        "hpa_yaml": hpa_yaml,
        "warnings": resource_warnings(m, reco, hpa),
        "savings": resource_savings(m, reco, n_replicas),
        "parsed": {
            "cpu_p95": format_cpu(m["cpu_p95"]), "cpu_max": format_cpu(m["cpu_max"]),
            "mem_p95": format_memory(m["mem_p95"]), "mem_max": format_memory(m["mem_max"]),
        },
        "conv": {
            "cpu_p95_cores": round(m["cpu_p95"] / 1000, 3),
            "cpu_max_cores": round(m["cpu_max"] / 1000, 3),
            "mem_p95_mi": round(m["mem_p95"] / MI),
            "mem_p95_gi": round(m["mem_p95"] / GI, 2),
            "mem_p95_bytes": m["mem_p95"],
            "mem_max_mi": round(m["mem_max"] / MI),
        },
        "fmt": {
            "req_cpu": format_cpu(reco["req_cpu"]), "lim_cpu": format_cpu(reco["lim_cpu"]),
            "req_mem": format_memory(reco["req_mem"]), "lim_mem": format_memory(reco["lim_mem"]),
        },
    }
    log.info("resources cpu_p95=%s mem_p95=%s replicas=%s", cpu_p95, mem_p95, replicas)
    return templates.TemplateResponse(request, "resources.html", ctx)
