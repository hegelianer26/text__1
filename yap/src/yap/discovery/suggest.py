from __future__ import annotations

from dataclasses import dataclass

from yap.discovery.parser import MetricFamilyInfo
from yap.inventory.compose import ComposeService


@dataclass(frozen=True)
class InspectionResult:
    service_name: str
    status: str
    metrics_endpoint: str | None
    container_port: int | None
    published_port: int | None
    error: str | None
    metric_families: list[MetricFamilyInfo]


def detect_profiles(metric_families: list[MetricFamilyInfo]) -> list[str]:
    names = {family.name for family in metric_families}
    profiles: list[str] = []

    if {"http_requests_total", "http_request_duration_seconds"}.issubset(names):
        profiles.append("http_server")

    if {"outbound_http_requests_total", "outbound_http_request_duration_seconds"}.issubset(names):
        profiles.append("http_client")

    if {"db_queries_total", "db_query_duration_seconds", "db_ready"}.issubset(names):
        profiles.append("postgres_client")

    if {"orders_created_total", "orders_read_total"}.issubset(names) or "orders_in_db" in names:
        profiles.append("business_orders")

    if {"pg_stat_activity_count", "pg_stat_database_xact_commit", "pg_stat_database_xact_rollback"}.issubset(names):
        profiles.append("postgres_exporter")

    if {"node_cpu_seconds_total", "node_load1", "node_memory_MemAvailable_bytes"}.issubset(names):
        profiles.append("node_exporter")

    if {"container_cpu_usage_seconds_total", "container_memory_usage_bytes"}.issubset(names):
        profiles.append("cadvisor")

    if "prometheus_build_info" in names or "prometheus_engine_query_duration_seconds" in names:
        profiles.append("prometheus_self")

    return profiles


def build_inventory_document(results: list[InspectionResult]) -> dict:
    services: dict[str, dict] = {}

    for result in results:
        service_doc: dict = {
            "status": result.status,
            "metrics_endpoint": result.metrics_endpoint,
            "container_port": result.container_port,
            "published_port": result.published_port,
        }

        if result.error:
            service_doc["error"] = result.error

        if result.status == "ok":
            service_doc["metric_family_count"] = len(result.metric_families)
            service_doc["metric_families"] = [
                {
                    **({"help": family.help} if family.help else {}),
                    "name": family.name,
                    "type": family.type,
                    **({"parts": family.parts} if family.parts else {}),
                    **({"labels": family.labels} if family.labels else {}),
                    **({"label_values_sample": family.label_values_sample} if family.label_values_sample else {}),
                    "sample_count": family.sample_count,
                }
                for family in result.metric_families
            ]

        services[result.service_name] = service_doc

    return {"services": services}


def _ensure_service_entry(doc: dict, service_name: str) -> dict:
    return doc.setdefault(service_name, {"modules": []})


def _add_module(service_entry: dict, module_name: str) -> None:
    modules = service_entry.setdefault("modules", [])
    if module_name not in modules:
        modules.append(module_name)


def _map_exporter_to_logical_service(
    exporter_service_name: str,
    inventory: dict[str, ComposeService],
) -> str:
    suffix = "-exporter"
    if exporter_service_name.endswith(suffix):
        base = exporter_service_name[: -len(suffix)]
        if base in inventory:
            return base
    return exporter_service_name


def build_suggested_config(
    inventory: dict[str, ComposeService],
    results: list[InspectionResult],
) -> dict:
    telemetry = {
        "host_metrics": False,
        "container_metrics": False,
        "postgres_metrics": False,
        "prometheus_self_metrics": False,
    }

    services_doc: dict[str, dict] = {}

    detected_by_service: dict[str, list[str]] = {}
    for result in results:
        if result.status != "ok":
            continue
        detected_by_service[result.service_name] = detect_profiles(result.metric_families)

    for service_name, profiles in detected_by_service.items():
        if "node_exporter" in profiles:
            telemetry["host_metrics"] = True
            continue

        if "cadvisor" in profiles:
            telemetry["container_metrics"] = True
            continue

        if "prometheus_self" in profiles:
            telemetry["prometheus_self_metrics"] = True
            continue

        if "postgres_exporter" in profiles:
            telemetry["postgres_metrics"] = True

            logical_service = _map_exporter_to_logical_service(service_name, inventory)
            service_entry = _ensure_service_entry(services_doc, logical_service)
            _add_module(service_entry, "postgres_exporter")

            exporter_compose_service = inventory.get(service_name)
            exporter_port = exporter_compose_service.ports[0] if exporter_compose_service and exporter_compose_service.ports else None

            service_entry["exporter_service"] = service_name
            if exporter_port is not None:
                service_entry["exporter_port"] = exporter_port

            continue

        service_entry = _ensure_service_entry(services_doc, service_name)

        if "http_server" in profiles:
            _add_module(service_entry, "http_server")

        if "http_client" in profiles:
            _add_module(service_entry, "http_client")

        if "postgres_client" in profiles:
            _add_module(service_entry, "postgres_client")

        if "business_orders" in profiles:
            _add_module(service_entry, "business_orders")

        compose_service = inventory.get(service_name)
        if compose_service and compose_service.ports:
            service_entry["metrics_port"] = compose_service.ports[0]

    if telemetry["container_metrics"]:
        for service_name, service_entry in services_doc.items():
            if service_name in inventory:
                _add_module(service_entry, "container_metrics")

    suggested = {
        "version": 1,
        "prometheus": {
            "url": "http://prometheus:9090",
            "job_label": "job",
            "scrape_interval": "5s",
            "evaluation_interval": "5s",
        },
        "telemetry": telemetry,
        "alerts": {
            "enabled": True,
            "target_down_for": "2m",
            "db_not_ready_for": "2m",
            "http_error_rate_threshold": 0.05,
            "http_latency_p95_threshold_seconds": 0.75,
            "host_high_cpu_threshold_percent": 90.0,
            "host_high_cpu_for": "5m",
        },
        "services": {name: services_doc[name] for name in sorted(services_doc.keys())},
    }

    return suggested