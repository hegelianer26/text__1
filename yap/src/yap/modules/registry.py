from __future__ import annotations

import re
from collections import OrderedDict

from yap.config.schema import AlertsConfig
from yap.modules.base import AlertRuleSpec, Module, PanelSpec, RequirementSpec

APP_SCRAPE_MODULES = {
    "http_server",
    "http_client",
    "postgres_client",
    "business_orders",
}


def _sanitize_alert_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", name)


def _dedupe_panels(panels: list[PanelSpec]) -> list[PanelSpec]:
    seen: set[tuple[str, str, str]] = set()
    result: list[PanelSpec] = []
    for panel in panels:
        key = (panel.title, panel.expr, panel.panel_type)
        if key in seen:
            continue
        seen.add(key)
        result.append(panel)
    return result


def _dedupe_requirements(items: list[RequirementSpec]) -> list[RequirementSpec]:
    seen: set[str] = set()
    result: list[RequirementSpec] = []
    for item in items:
        if item.id in seen:
            continue
        seen.add(item.id)
        result.append(item)
    return result


def _dedupe_alerts(items: list[AlertRuleSpec]) -> list[AlertRuleSpec]:
    seen: set[str] = set()
    result: list[AlertRuleSpec] = []
    for item in items:
        if item.alert in seen:
            continue
        seen.add(item.alert)
        result.append(item)
    return result


class HttpServerModule:
    name = "http_server"

    def dashboard_sections(self, job_label: str) -> dict[str, list[PanelSpec]]:
        sel = f'{{{job_label}="$job"}}'
        err_sel = f'{{{job_label}="$job",status=~"5.."}}'
        return {
            "Обзор": [
                PanelSpec("up", f"max(up{sel})", "stat"),
            ],
            "Прикладные метрики": [
                PanelSpec("http requests/s", f"sum(rate(http_requests_total{sel}[5m]))"),
                PanelSpec("http errors/s (5xx)", f"sum(rate(http_requests_total{err_sel}[5m]))"),
                PanelSpec(
                    "http latency p95",
                    f"histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{sel}[5m])) by (le))",
                ),
                PanelSpec("inflight requests", f"sum(http_inflight_requests{sel})"),
                PanelSpec("response bytes/s", f"sum(rate(http_response_bytes_total{sel}[5m]))"),
            ],
        }

    def requirements(self, job_label: str) -> list[RequirementSpec]:
        sel = f'{{{job_label}="$job"}}'
        err_sel = f'{{{job_label}="$job",status=~"5.."}}'
        return [
            RequirementSpec("up", "Доступность таргета (up)", "must", [f"max(up{sel})"]),
            RequirementSpec("http_requests", "Интенсивность HTTP-запросов", "should", [f"sum(rate(http_requests_total{sel}[5m]))"]),
            RequirementSpec("http_errors", "HTTP-ошибки 5xx", "should", [f"sum(rate(http_requests_total{err_sel}[5m]))"]),
            RequirementSpec(
                "http_latency",
                "Задержка HTTP p95",
                "should",
                [f"histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{sel}[5m])) by (le))"],
            ),
            RequirementSpec("inflight_requests", "Текущие inflight-запросы", "should", [f"sum(http_inflight_requests{sel})"]),
        ]

    def alerts(self, job_label: str, service_name: str, alerts_cfg: AlertsConfig) -> list[AlertRuleSpec]:
        sel = f'{{{job_label}="{service_name}"}}'
        err_sel = f'{{{job_label}="{service_name}",status=~"5.."}}'
        safe = _sanitize_alert_name(service_name)
        return [
            AlertRuleSpec(
                alert=f"{safe}_TargetDown",
                expr=f"max(up{sel}) == 0",
                duration=alerts_cfg.target_down_for,
                labels={"severity": "critical", "service": service_name},
                annotations={
                    "summary": f"{service_name} is down",
                    "description": f"Prometheus target for {service_name} is unavailable.",
                },
            ),
            AlertRuleSpec(
                alert=f"{safe}_HighHttpErrorRate",
                expr=(
                    f'(sum(rate(http_requests_total{err_sel}[5m])) / '
                    f'clamp_min(sum(rate(http_requests_total{sel}[5m])), 0.001)) '
                    f'> {alerts_cfg.http_error_rate_threshold}'
                ),
                duration="5m",
                labels={"severity": "warning", "service": service_name},
                annotations={
                    "summary": f"{service_name} high HTTP 5xx rate",
                    "description": "Error rate exceeded configured threshold.",
                },
            ),
            AlertRuleSpec(
                alert=f"{safe}_HighHttpLatencyP95",
                expr=(
                    f'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{sel}[5m])) by (le)) '
                    f'> {alerts_cfg.http_latency_p95_threshold_seconds}'
                ),
                duration="5m",
                labels={"severity": "warning", "service": service_name},
                annotations={
                    "summary": f"{service_name} high HTTP latency p95",
                    "description": "HTTP p95 latency exceeded configured threshold.",
                },
            ),
        ]

    def telemetry_needs(self) -> set[str]:
        return {"app_scrape"}


class HttpClientModule:
    name = "http_client"

    def dashboard_sections(self, job_label: str) -> dict[str, list[PanelSpec]]:
        sel = f'{{{job_label}="$job"}}'
        outbound_err_sel = f'{{{job_label}="$job",status=~"5..|error"}}'
        return {
            "Обзор": [
                PanelSpec("downstream up", f"min(downstream_up{sel})", "stat"),
            ],
            "Прикладные метрики": [
                PanelSpec("outbound requests/s", f"sum(rate(outbound_http_requests_total{sel}[5m]))"),
                PanelSpec("outbound errors/s", f"sum(rate(outbound_http_requests_total{outbound_err_sel}[5m]))"),
                PanelSpec(
                    "outbound latency p95",
                    f"histogram_quantile(0.95, sum(rate(outbound_http_request_duration_seconds_bucket{sel}[5m])) by (le))",
                ),
                PanelSpec("outbound response bytes/s", f"sum(rate(outbound_http_response_bytes_total{sel}[5m]))"),
                PanelSpec("proxy actions/s", f"sum(rate(proxy_actions_total{sel}[5m]))"),
            ],
        }

    def requirements(self, job_label: str) -> list[RequirementSpec]:
        sel = f'{{{job_label}="$job"}}'
        outbound_err_sel = f'{{{job_label}="$job",status=~"5..|error"}}'
        return [
            RequirementSpec("downstream_up", "Доступность downstream", "should", [f"min(downstream_up{sel})"]),
            RequirementSpec("outbound_requests", "Исходящие HTTP-запросы", "should", [f"sum(rate(outbound_http_requests_total{sel}[5m]))"]),
            RequirementSpec("outbound_errors", "Ошибки downstream-вызовов", "should", [f"sum(rate(outbound_http_requests_total{outbound_err_sel}[5m]))"]),
            RequirementSpec(
                "outbound_latency",
                "Задержка downstream-вызовов p95",
                "should",
                [f"histogram_quantile(0.95, sum(rate(outbound_http_request_duration_seconds_bucket{sel}[5m])) by (le))"],
            ),
        ]

    def alerts(self, job_label: str, service_name: str, alerts_cfg: AlertsConfig) -> list[AlertRuleSpec]:
        sel = f'{{{job_label}="{service_name}"}}'
        safe = _sanitize_alert_name(service_name)
        return [
            AlertRuleSpec(
                alert=f"{safe}_DownstreamUnavailable",
                expr=f"min(downstream_up{sel}) == 0",
                duration="2m",
                labels={"severity": "warning", "service": service_name},
                annotations={
                    "summary": f"{service_name} downstream unavailable",
                    "description": "At least one downstream dependency is unavailable.",
                },
            ),
        ]

    def telemetry_needs(self) -> set[str]:
        return {"app_scrape"}


class PostgresClientModule:
    name = "postgres_client"

    def dashboard_sections(self, job_label: str) -> dict[str, list[PanelSpec]]:
        ok_sel = f'{{{job_label}="$job",status="ok"}}'
        err_sel = f'{{{job_label}="$job",status="error"}}'
        sel = f'{{{job_label}="$job"}}'
        return {
            "Обзор": [
                PanelSpec("db ready", f"max(db_ready{sel})", "stat"),
            ],
            "Прикладные метрики": [
                PanelSpec("db queries/s", f"sum(rate(db_queries_total{ok_sel}[5m]))"),
                PanelSpec("db errors/s", f"sum(rate(db_queries_total{err_sel}[5m]))"),
                PanelSpec(
                    "db latency p95",
                    f'histogram_quantile(0.95, sum(rate(db_query_duration_seconds_bucket{{{job_label}="$job"}}[5m])) by (le, operation))',
                ),
            ],
        }

    def requirements(self, job_label: str) -> list[RequirementSpec]:
        ok_sel = f'{{{job_label}="$job",status="ok"}}'
        err_sel = f'{{{job_label}="$job",status="error"}}'
        sel = f'{{{job_label}="$job"}}'
        return [
            RequirementSpec("db_ready", "Доступность БД на уровне приложения", "must", [f"max(db_ready{sel})"]),
            RequirementSpec("db_queries", "Успешные запросы к БД", "should", [f"sum(rate(db_queries_total{ok_sel}[5m]))"]),
            RequirementSpec("db_errors", "Ошибки запросов к БД", "should", [f"sum(rate(db_queries_total{err_sel}[5m]))"]),
            RequirementSpec(
                "db_latency",
                "Задержка запросов к БД p95",
                "should",
                [f'histogram_quantile(0.95, sum(rate(db_query_duration_seconds_bucket{{{job_label}="$job"}}[5m])) by (le, operation))'],
            ),
        ]

    def alerts(self, job_label: str, service_name: str, alerts_cfg: AlertsConfig) -> list[AlertRuleSpec]:
        safe = _sanitize_alert_name(service_name)
        return [
            AlertRuleSpec(
                alert=f"{safe}_DbNotReady",
                expr=f'max(db_ready{{{job_label}="{service_name}"}}) == 0',
                duration=alerts_cfg.db_not_ready_for,
                labels={"severity": "critical", "service": service_name},
                annotations={
                    "summary": f"{service_name} database is not ready",
                    "description": "Application-level DB readiness is zero.",
                },
            ),
        ]

    def telemetry_needs(self) -> set[str]:
        return {"app_scrape"}


class BusinessOrdersModule:
    name = "business_orders"

    def dashboard_sections(self, job_label: str) -> dict[str, list[PanelSpec]]:
        sel = f'{{{job_label}="$job"}}'
        return {
            "Обзор": [
                PanelSpec("orders in db", f"max(orders_in_db{sel})", "stat"),
                PanelSpec("quantity sum", f"max(orders_quantity_sum{sel})", "stat"),
            ],
            "Прикладные метрики": [
                PanelSpec("orders created/s", f"sum(rate(orders_created_total{sel}[5m]))"),
                PanelSpec("orders read/s", f"sum(rate(orders_read_total{sel}[5m]))"),
                PanelSpec("summary requests/s", f"sum(rate(orders_summary_requests_total{sel}[5m]))"),
                PanelSpec("slow requests/s", f"sum(rate(slow_requests_total{sel}[5m]))"),
                PanelSpec("intentional errors/s", f"sum(rate(intentional_errors_total{sel}[5m]))"),
            ],
        }

    def requirements(self, job_label: str) -> list[RequirementSpec]:
        sel = f'{{{job_label}="$job"}}'
        return [
            RequirementSpec("orders_in_db", "Количество заказов в БД", "should", [f"max(orders_in_db{sel})"]),
            RequirementSpec("orders_created", "Создание заказов", "should", [f"sum(rate(orders_created_total{sel}[5m]))"]),
            RequirementSpec("orders_read", "Чтение заказов", "should", [f"sum(rate(orders_read_total{sel}[5m]))"]),
            RequirementSpec("slow_requests", "Медленные запросы", "should", [f"sum(rate(slow_requests_total{sel}[5m]))"]),
        ]

    def alerts(self, job_label: str, service_name: str, alerts_cfg: AlertsConfig) -> list[AlertRuleSpec]:
        return []

    def telemetry_needs(self) -> set[str]:
        return {"app_scrape"}


class PostgresExporterModule:
    name = "postgres_exporter"

    def dashboard_sections(self, job_label: str) -> dict[str, list[PanelSpec]]:
        sel = f'{{{job_label}="$job"}}'
        return {
            "Обзор": [
                PanelSpec("up", f"max(up{sel})", "stat"),
                PanelSpec("connections", f"pg_stat_activity_count{sel}", "stat"),
            ],
            "Прикладные метрики": [
                PanelSpec(
                    "transactions/s",
                    f"sum(rate(pg_stat_database_xact_commit{sel}[5m])) + sum(rate(pg_stat_database_xact_rollback{sel}[5m]))",
                ),
                PanelSpec("deadlocks/s", f"sum(rate(pg_stat_database_deadlocks{sel}[5m]))"),
                PanelSpec(
                    "cache hit ratio",
                    f"sum(rate(pg_stat_database_blks_hit{sel}[5m])) / (sum(rate(pg_stat_database_blks_hit{sel}[5m])) + sum(rate(pg_stat_database_blks_read{sel}[5m])))",
                ),
            ],
        }

    def requirements(self, job_label: str) -> list[RequirementSpec]:
        sel = f'{{{job_label}="$job"}}'
        return [
            RequirementSpec("up", "Доступность postgres_exporter (up)", "must", [f"max(up{sel})"]),
            RequirementSpec("pg_connections", "Активные соединения", "must", [f"pg_stat_activity_count{sel}"]),
            RequirementSpec(
                "pg_transactions",
                "Скорость транзакций",
                "should",
                [f"sum(rate(pg_stat_database_xact_commit{sel}[5m])) + sum(rate(pg_stat_database_xact_rollback{sel}[5m]))"],
            ),
            RequirementSpec("pg_deadlocks", "Скорость дедлоков", "should", [f"sum(rate(pg_stat_database_deadlocks{sel}[5m]))"]),
        ]

    def alerts(self, job_label: str, service_name: str, alerts_cfg: AlertsConfig) -> list[AlertRuleSpec]:
        safe = _sanitize_alert_name(service_name)
        return [
            AlertRuleSpec(
                alert=f"{safe}_TargetDown",
                expr=f'max(up{{{job_label}="{service_name}"}}) == 0',
                duration=alerts_cfg.target_down_for,
                labels={"severity": "critical", "service": service_name},
                annotations={
                    "summary": f"{service_name} exporter is down",
                    "description": f"Prometheus target for exporter job {service_name} is unavailable.",
                },
            ),
        ]

    def telemetry_needs(self) -> set[str]:
        return {"postgres_exporter_scrape"}


class ContainerMetricsModule:
    name = "container_metrics"

    def dashboard_sections(self, job_label: str) -> dict[str, list[PanelSpec]]:
        cadvisor_sel = '{job="cadvisor",service="$job"}'
        return {
            "Контейнерные метрики (cAdvisor)": [
                PanelSpec("container cpu usage", f"sum(rate(container_cpu_usage_seconds_total{cadvisor_sel}[5m]))"),
                PanelSpec("container memory usage", f"sum(container_memory_usage_bytes{cadvisor_sel})"),
                PanelSpec("container net rx/s", f"sum(rate(container_network_receive_bytes_total{cadvisor_sel}[5m]))"),
                PanelSpec("container net tx/s", f"sum(rate(container_network_transmit_bytes_total{cadvisor_sel}[5m]))"),
            ],
        }

    def requirements(self, job_label: str) -> list[RequirementSpec]:
        cadvisor_sel = '{job="cadvisor",service="$job"}'
        return [
            RequirementSpec("container_cpu", "Потребление CPU контейнером", "should", [f"sum(rate(container_cpu_usage_seconds_total{cadvisor_sel}[5m]))"]),
            RequirementSpec("container_mem", "Потребление памяти контейнером", "should", [f"sum(container_memory_usage_bytes{cadvisor_sel})"]),
            RequirementSpec("container_rx", "Входящий сетевой трафик контейнера", "should", [f"sum(rate(container_network_receive_bytes_total{cadvisor_sel}[5m]))"]),
            RequirementSpec("container_tx", "Исходящий сетевой трафик контейнера", "should", [f"sum(rate(container_network_transmit_bytes_total{cadvisor_sel}[5m]))"]),
        ]

    def alerts(self, job_label: str, service_name: str, alerts_cfg: AlertsConfig) -> list[AlertRuleSpec]:
        return []

    def telemetry_needs(self) -> set[str]:
        return {"cadvisor"}


class HostMetricsModule:
    name = "host_metrics"

    def dashboard_sections(self, job_label: str) -> dict[str, list[PanelSpec]]:
        return {
            "Обзор": [
                PanelSpec("node up", 'max(up{job="$job"})', "stat"),
            ],
            "Системные метрики хоста (node_exporter)": [
                PanelSpec("cpu busy %", '100 * (1 - avg(rate(node_cpu_seconds_total{job="$job",mode="idle"}[5m])))'),
                PanelSpec("load1", 'node_load1{job="$job"}'),
                PanelSpec("mem available", 'node_memory_MemAvailable_bytes{job="$job"}'),
                PanelSpec("disk free total", 'sum(node_filesystem_avail_bytes{job="$job",fstype!=""})'),
                PanelSpec("net rx/s", 'sum(rate(node_network_receive_bytes_total{job="$job"}[5m]))'),
                PanelSpec("net tx/s", 'sum(rate(node_network_transmit_bytes_total{job="$job"}[5m]))'),
            ],
        }

    def requirements(self, job_label: str) -> list[RequirementSpec]:
        return [
            RequirementSpec("node_up", "Доступность node_exporter", "must", ['max(up{job="$job"})']),
            RequirementSpec("node_cpu", "Загрузка CPU хоста", "should", ['100 * (1 - avg(rate(node_cpu_seconds_total{job="$job",mode="idle"}[5m])))']),
            RequirementSpec("node_load", "Load average хоста", "should", ['node_load1{job="$job"}']),
            RequirementSpec("node_mem", "Доступная память хоста", "should", ['node_memory_MemAvailable_bytes{job="$job"}']),
            RequirementSpec("node_disk", "Свободное дисковое пространство хоста", "should", ['sum(node_filesystem_avail_bytes{job="$job",fstype!=""})']),
        ]

    def alerts(self, job_label: str, service_name: str, alerts_cfg: AlertsConfig) -> list[AlertRuleSpec]:
        return [
            AlertRuleSpec(
                alert="HostTargetDown",
                expr='max(up{job="node"}) == 0',
                duration=alerts_cfg.target_down_for,
                labels={"severity": "critical", "service": "host"},
                annotations={
                    "summary": "node-exporter is down",
                    "description": "Host metrics target is unavailable.",
                },
            ),
            AlertRuleSpec(
                alert="HostHighCpu",
                expr=(
                    '100 * (1 - avg(rate(node_cpu_seconds_total{job="node",mode="idle"}[5m]))) '
                    f'> {alerts_cfg.host_high_cpu_threshold_percent}'
                ),
                duration=alerts_cfg.host_high_cpu_for,
                labels={"severity": "warning", "service": "host"},
                annotations={
                    "summary": "Host CPU usage is high",
                    "description": "Host CPU busy percentage exceeded configured threshold.",
                },
            ),
        ]

    def telemetry_needs(self) -> set[str]:
        return {"node_exporter"}


MODULE_REGISTRY: dict[str, Module] = {
    "http_server": HttpServerModule(),
    "http_client": HttpClientModule(),
    "postgres_client": PostgresClientModule(),
    "postgres_exporter": PostgresExporterModule(),
    "business_orders": BusinessOrdersModule(),
    "container_metrics": ContainerMetricsModule(),
}

HOST_MODULE = HostMetricsModule()


def _active_module_names(
    modules: list[str],
    *,
    container_metrics_enabled: bool,
    postgres_metrics_enabled: bool,
) -> list[str]:
    result: list[str] = []
    for module_name in modules:
        if module_name == "container_metrics" and not container_metrics_enabled:
            continue
        if module_name == "postgres_exporter" and not postgres_metrics_enabled:
            continue
        result.append(module_name)
    return result


def compose_service_sections(
    modules: list[str],
    *,
    job_label: str,
    container_metrics_enabled: bool,
    postgres_metrics_enabled: bool,
) -> list[tuple[str, list[PanelSpec]]]:
    section_order = [
        "Обзор",
        "Прикладные метрики",
        "Контейнерные метрики (cAdvisor)",
    ]
    merged: OrderedDict[str, list[PanelSpec]] = OrderedDict((name, []) for name in section_order)

    for module_name in _active_module_names(
        modules,
        container_metrics_enabled=container_metrics_enabled,
        postgres_metrics_enabled=postgres_metrics_enabled,
    ):
        module = MODULE_REGISTRY[module_name]
        for section_name, panels in module.dashboard_sections(job_label).items():
            merged.setdefault(section_name, [])
            merged[section_name].extend(panels)

    return [
        (section_name, _dedupe_panels(panels))
        for section_name, panels in merged.items()
        if panels
    ]


def compose_service_requirements(
    modules: list[str],
    *,
    job_label: str,
    container_metrics_enabled: bool,
    postgres_metrics_enabled: bool,
) -> list[RequirementSpec]:
    items: list[RequirementSpec] = []
    for module_name in _active_module_names(
        modules,
        container_metrics_enabled=container_metrics_enabled,
        postgres_metrics_enabled=postgres_metrics_enabled,
    ):
        module = MODULE_REGISTRY[module_name]
        items.extend(module.requirements(job_label))
    return _dedupe_requirements(items)


def compose_service_alerts(
    service_name: str,
    modules: list[str],
    *,
    job_label: str,
    alerts_cfg: AlertsConfig,
    container_metrics_enabled: bool,
    postgres_metrics_enabled: bool,
    enabled: bool,
) -> list[AlertRuleSpec]:
    if not enabled:
        return []

    items: list[AlertRuleSpec] = []
    for module_name in _active_module_names(
        modules,
        container_metrics_enabled=container_metrics_enabled,
        postgres_metrics_enabled=postgres_metrics_enabled,
    ):
        module = MODULE_REGISTRY[module_name]
        items.extend(module.alerts(job_label, service_name, alerts_cfg))
    return _dedupe_alerts(items)


def host_sections() -> list[tuple[str, list[PanelSpec]]]:
    data = HOST_MODULE.dashboard_sections("job")
    return [(name, _dedupe_panels(panels)) for name, panels in data.items() if panels]


def host_requirements() -> list[RequirementSpec]:
    return HOST_MODULE.requirements("job")


def host_alerts(alerts_cfg: AlertsConfig, enabled: bool) -> list[AlertRuleSpec]:
    if not enabled:
        return []
    return _dedupe_alerts(HOST_MODULE.alerts("job", "host", alerts_cfg))