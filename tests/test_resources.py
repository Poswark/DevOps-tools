"""Pruebas de la card de recursos y HPA."""
import pytest
from fastapi.testclient import TestClient

from main import (
    GI,
    MI,
    app,
    format_cpu,
    format_memory,
    parse_cpu,
    parse_memory,
    qos_class,
    recommend_hpa,
    recommend_resources,
    resource_savings,
    resource_warnings,
)

client = TestClient(app)


# ---------------------------------------------------------------- parseo
@pytest.mark.parametrize("text,esperado", [
    ("250m", 250),        # sufijo explicito
    ("1500m", 1500),
    (" 1 core ", 1000),   # palabra explicita
    ("0.5", 500),         # decimal suelto = cores
    ("2", 2000),          # entero suelto < 10 = cores
    ("350", 350),         # entero suelto >= 10 = millicores (como Dynatrace)
    ("850", 850),
])
def test_parse_cpu(text, esperado):
    assert parse_cpu(text) == esperado


def test_parse_cpu_numero_suelto_grande_es_millicores():
    """Regresion: '350' debe ser 350m, no 350 cores."""
    assert parse_cpu("350") == 350
    assert parse_cpu("350") == parse_cpu("350m")


def test_parse_cpu_cores_explicitos_ganan():
    assert parse_cpu("16 cores") == 16000


def test_parse_cpu_vacio_usa_default():
    assert parse_cpu("", default=99) == 99
    assert parse_cpu(None) is None


def test_parse_cpu_invalida():
    with pytest.raises(ValueError, match="CPU invalida"):
        parse_cpu("mucha")


@pytest.mark.parametrize("text,esperado", [
    ("512Mi", 512 * MI), ("2Gi", 2 * GI), ("1024M", 1024 * 10 ** 6),
    ("1.5G", 1_500_000_000), ("512MiB", 512 * MI),
    ("650", 650 * MI),        # numero suelto = MiB
    ("536870912b", 536870912),  # bytes solo con sufijo explicito
])
def test_parse_memory(text, esperado):
    assert parse_memory(text) == esperado


def test_parse_memory_numero_suelto_es_mib():
    """Regresion: '650' debe ser 650Mi, no 650 bytes."""
    assert parse_memory("650") == parse_memory("650Mi")


def test_parse_memory_none_usa_default():
    assert parse_memory(None) is None
    assert parse_memory(None, default=123) == 123
    assert parse_memory("", default=456) == 456


def test_parse_memory_invalida():
    with pytest.raises(ValueError, match="Memoria invalida"):
        parse_memory("dos gigas")


# ---------------------------------------------------------------- formato
@pytest.mark.parametrize("m,esperado", [(1000, "1"), (250, "250m"), (2000, "2"), (1500, "1500m")])
def test_format_cpu(m, esperado):
    assert format_cpu(m) == esperado


@pytest.mark.parametrize("b,esperado", [(2 * GI, "2Gi"), (512 * MI, "512Mi"), (64 * MI, "64Mi")])
def test_format_memory(b, esperado):
    assert format_memory(b) == esperado


def test_roundtrip_unidades():
    assert parse_memory(format_memory(576 * MI)) == 576 * MI
    assert parse_cpu(format_cpu(410)) == 410


# ---------------------------------------------------------------- right-sizing
def test_recommend_resources_caso_conocido():
    r = recommend_resources(350, 620, 480 * MI, 710 * MI)
    assert r["req_cpu"] == 410          # p95 350m + 15%, redondeado a 10m
    assert r["lim_cpu"] == 930          # max(620*1.5, 410*2)
    assert r["req_mem"] == 576 * MI     # p95 480Mi + 15%, redondeado a 32Mi
    assert r["lim_mem"] == 928 * MI     # max(710Mi*1.3, req*1.25)


@pytest.mark.parametrize("cpu_p95,cpu_max,mem_p95,mem_max", [
    (10, 15, 20 * MI, 30 * MI),
    (350, 620, 480 * MI, 710 * MI),
    (2500, 3800, 3 * GI, 4 * GI),
    (50, 50, 100 * MI, 100 * MI),
])
def test_limits_nunca_menores_que_requests(cpu_p95, cpu_max, mem_p95, mem_max):
    r = recommend_resources(cpu_p95, cpu_max, mem_p95, mem_max)
    assert r["lim_cpu"] >= r["req_cpu"]
    assert r["lim_mem"] >= r["req_mem"]


def test_limite_de_memoria_cubre_el_pico_observado():
    r = recommend_resources(100, 200, 500 * MI, 900 * MI)
    assert r["lim_mem"] >= 900 * MI


def test_pisos_minimos_para_apps_pequenas():
    r = recommend_resources(1, 1, 1 * MI, 1 * MI)
    assert r["req_cpu"] >= 10
    assert r["req_mem"] >= 64 * MI


def test_qos_class():
    assert qos_class(500, 500, 512 * MI, 512 * MI) == "Guaranteed"
    assert qos_class(500, 1000, 512 * MI, 512 * MI) == "Burstable"


# ---------------------------------------------------------------- HPA
def test_recommend_hpa_caso_conocido():
    h = recommend_hpa(cpu_p95_m=350, req_cpu_m=410, replicas=3,
                      tpm_avg=1200, tpm_peak=4500, target_util=70)
    assert h["min_replicas"] == 2
    assert h["max_replicas"] == 6
    assert h["target_util"] == 70
    assert h["tpm_per_pod_actual"] == 1500


def test_recommend_hpa_sin_datos():
    assert recommend_hpa(350, 410, 0, 100, 200) is None
    assert recommend_hpa(350, 410, 3, 100, 0) is None
    assert recommend_hpa(0, 410, 3, 100, 200) is None


def test_recommend_hpa_sin_capacidad_por_pod():
    """Si el request de CPU es cero, un pod no aguanta nada y no hay HPA que valga."""
    assert recommend_hpa(350, 0, 3, 1200, 4500, 70) is None


def test_recommend_hpa_minimo_dos_replicas():
    h = recommend_hpa(50, 100, 1, 1, 10, 70)
    assert h["min_replicas"] >= 2
    assert h["max_replicas"] > h["min_replicas"]


def test_hpa_crece_con_el_tpm_objetivo():
    """Con la misma medicion, pedir mas throughput futuro sube maxReplicas."""
    hoy = recommend_hpa(350, 410, 3, 1200, 4500, 70)
    doble = recommend_hpa(350, 410, 3, 1200, 4500, 70, tpm_target=9000)
    assert doble["max_replicas"] > hoy["max_replicas"]
    assert doble["tpm_objetivo"] == 9000


def test_hpa_objetivo_menor_al_pico_no_subdimensiona():
    h = recommend_hpa(350, 410, 3, 1200, 4500, 70, tpm_target=1000)
    assert h["tpm_objetivo"] == 4500


# ---------------------------------------------------------------- ahorro
def test_resource_savings_positivo():
    m = {"req_cpu_actual": 1000, "req_mem_actual": 2 * GI}
    s = resource_savings(m, {"req_cpu": 410, "req_mem": 576 * MI}, 3)
    assert s["cpu_cores"] == pytest.approx(1.77, abs=0.01)
    assert s["mem_gib"] > 0


def test_resource_savings_negativo_si_esta_corto():
    m = {"req_cpu_actual": 100, "req_mem_actual": 128 * MI}
    s = resource_savings(m, {"req_cpu": 410, "req_mem": 576 * MI}, 2)
    assert s["cpu_cores"] < 0
    assert s["mem_gib"] < 0


def test_resource_savings_sin_datos_actuales():
    assert resource_savings({}, {"req_cpu": 410, "req_mem": 576 * MI}, 3) is None


# ---------------------------------------------------------------- hallazgos
def _metricas(**extra):
    base = {"cpu_p95": 350, "cpu_max": 620, "mem_p95": 480 * MI, "mem_max": 710 * MI}
    base.update(extra)
    return base


def test_warning_throttling():
    m = _metricas(lim_cpu_actual=650)
    textos = " ".join(t for _, t in resource_warnings(m, recommend_resources(350, 620, 480 * MI, 710 * MI), None))
    assert "throttling" in textos


def test_warning_oom():
    m = _metricas(lim_mem_actual=750 * MI)
    textos = " ".join(t for _, t in resource_warnings(m, recommend_resources(350, 620, 480 * MI, 710 * MI), None))
    assert "OOMKilled" in textos


def test_warning_sobreaprovisionado():
    m = _metricas(req_cpu_actual=2000)
    textos = " ".join(t for _, t in resource_warnings(m, recommend_resources(350, 620, 480 * MI, 710 * MI), None))
    assert "p95" in textos


def test_warning_picos_de_memoria():
    """Si el maximo duplica el p95, se avisa que la app tiene picos marcados."""
    m = _metricas(mem_p95=300 * MI, mem_max=900 * MI)
    reco = recommend_resources(350, 620, 300 * MI, 900 * MI)
    textos = " ".join(t for _, t in resource_warnings(m, reco, None))
    assert "picos" in textos


def test_warning_unidad_de_cpu_olvidada():
    """350 cores casi siempre significa que se escribio '350' queriendo '350m'."""
    m = _metricas(cpu_p95=350_000, cpu_max=850_000)
    reco = recommend_resources(350_000, 850_000, 480 * MI, 710 * MI)
    textos = " ".join(t for _, t in resource_warnings(m, reco, None))
    assert "cores" in textos and "350m" in textos


def test_warning_unidad_de_memoria_olvidada():
    m = _metricas(mem_p95=500 * GI, mem_max=600 * GI)
    reco = recommend_resources(350, 620, 500 * GI, 600 * GI)
    textos = " ".join(t for _, t in resource_warnings(m, reco, None))
    assert "650Mi" in textos


def test_warning_maximo_menor_que_p95():
    m = _metricas(cpu_max=100, mem_max=100 * MI)
    reco = recommend_resources(350, 100, 480 * MI, 100 * MI)
    textos = " ".join(t for _, t in resource_warnings(m, reco, None))
    assert textos.count("invertidos") == 2


def test_siempre_reporta_qos():
    niveles = resource_warnings(_metricas(), recommend_resources(350, 620, 480 * MI, 710 * MI), None)
    assert any(lvl == "ok" and "QoS" in txt for lvl, txt in niveles)


def test_nota_de_hpa_sobre_requests():
    hpa = recommend_hpa(350, 410, 3, 1200, 4500, 70)
    textos = " ".join(t for _, t in resource_warnings(_metricas(), recommend_resources(350, 620, 480 * MI, 710 * MI), hpa))
    assert "request" in textos


# ---------------------------------------------------------------- rutas
def test_get_resources():
    r = client.get("/resources")
    assert r.status_code == 200
    assert "Recursos y HPA" in r.text


def test_post_resources_calcula():
    r = client.post("/resources", data={
        "cpu_p95": "350m", "cpu_max": "620m",
        "mem_p95": "480Mi", "mem_max": "710Mi",
        "replicas": "3", "tpm_avg": "1200", "tpm_peak": "4500",
        "target_util": "70", "workload": "pagos-api",
    })
    assert r.status_code == 200
    assert "410m" in r.text and "930m" in r.text
    assert "576Mi" in r.text and "928Mi" in r.text
    assert "HorizontalPodAutoscaler" in r.text
    assert "pagos-api" in r.text


def test_post_resources_muestra_la_interpretacion():
    """El usuario debe ver que entendio la herramienta, con o sin unidades."""
    r = client.post("/resources", data={
        "cpu_p95": "350", "cpu_max": "850", "mem_p95": "650", "mem_max": "710",
    })
    assert r.status_code == 200
    assert "Se interpretaron tus datos" in r.text
    assert "350m" in r.text and "650Mi" in r.text


def test_post_resources_numeros_sueltos_dan_valores_sensatos():
    """Regresion del caso real: 350 / 850 / 650 / 710 sin unidades."""
    r = client.post("/resources", data={
        "cpu_p95": "350", "cpu_max": "850", "mem_p95": "650", "mem_max": "710",
    })
    assert "410m" in r.text          # y no 402500m
    assert "768Mi" in r.text         # y no 64Mi
    assert "402500m" not in r.text


def test_post_resources_sin_tpm_no_arma_hpa():
    r = client.post("/resources", data={"cpu_p95": "350m", "mem_p95": "480Mi"})
    assert r.status_code == 200
    assert "410m" in r.text
    assert "HorizontalPodAutoscaler" not in r.text


def test_post_resources_faltan_obligatorios():
    r = client.post("/resources", data={"cpu_p95": "", "mem_p95": ""})
    assert r.status_code == 200
    assert "obligatorios" in r.text


def test_post_resources_unidad_invalida():
    r = client.post("/resources", data={"cpu_p95": "mucha", "mem_p95": "480Mi"})
    assert r.status_code == 200
    assert "CPU invalida" in r.text


def test_post_resources_muestra_ahorro():
    r = client.post("/resources", data={
        "cpu_p95": "350m", "cpu_max": "620m", "mem_p95": "480Mi", "mem_max": "710Mi",
        "replicas": "3", "req_cpu_actual": "1", "req_mem_actual": "2Gi",
        "lim_cpu_actual": "2", "lim_mem_actual": "2Gi",
    })
    assert r.status_code == 200
    assert "cores" in r.text
