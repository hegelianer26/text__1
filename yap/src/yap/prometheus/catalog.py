from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Level = Literal["must", "should"]


@dataclass(frozen=True)
class Requirement:
    id: str
    title: str
    level: Level
    promql_templates: list[str]
    note: str | None = None


def _dedupe(items: list[Requirement]) -> list[Requirement]:
    seen: set[str] = set()
    result: list[Requirement] = []
    for item in items:
        if item.id in seen:
            continue
        seen.add(item.id)
        result.append(item)
    return result


def requirements_for_modules(modules: list[str], job_label: str = "job") -> list[Requirement]:
    sel = f'{{{job_label}="$job"}}'
    err_sel = f'{{{job_label}="$job",status=~"5.."}}'
    outbound_err_sel = f'{{{job_label}="$job",status=~"5..|error"}}'
    db_ok_sel = f'{{{job_label}="$job",status="ok"}}'
    db_err_sel = f'{{{job_label}="$job",status="error"}}'
    cadvisor_sel = '{job="cadvisor",service="$job"}'

    reqs: list[Requirement] = []

    if any(m in modules for m in ["http_server", "http_client", "postgres_client", "business_orders", "postgres_exporter"]):
        reqs.append(Requirement("up", "Доступность таргета (up)", "must", [f"max(up{sel})"]))

    if "http_server" in modules:
        reqs.extend(
            [
                Requirement("http_requests", "Интенсивность HTTP-запросов", "should", [f"sum(rate(http_requests_total{sel}[5m]))"]),
                Requirement("http_errors", "HTTP-ошибки 5xx", "should", [f"sum(rate(http_requests_total{err_sel}[5m]))"]),
                Requirement(
                    "http_latency",
                    "Задержка HTTP p95",
                    "should",
                    [f"histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{sel}[5m])) by (le))"],
                ),
                Requirement("inflight_requests", "Текущие inflight-запросы", "should", [f"sum(http_inflight_requests{sel})"]),
            ]
        )

    if "http_client" in modules:
        reqs.extend(
            [
                Requirement("downstream_up", "Доступность downstream", "should", [f"min(downstream_up{sel})"]),
                Requirement("outbound_requests", "Исходящие HTTP-запросы", "should", [f"sum(rate(outbound_http_requests_total{sel}[5m]))"]),
                Requirement("outbound_errors", "Ошибки downstream-вызовов", "should", [f"sum(rate(outbound_http_requests_total{outbound_err_sel}[5m]))"]),
                Requirement(
                    "outbound_latency",
                    "Задержка downstream-вызовов p95",
                    "should",
                    [f"histogram_quantile(0.95, sum(rate(outbound_http_request_duration_seconds_bucket{sel}[5m])) by (le))"],
                ),
            ]
        )

    if "postgres_client" in modules:
        reqs.extend(
            [
                Requirement("db_ready", "Доступность БД на уровне приложения", "must", [f"max(db_ready{sel})"]),
                Requirement("db_queries", "Успешные запросы к БД", "should", [f"sum(rate(db_queries_total{db_ok_sel}[5m]))"]),
                Requirement("db_errors", "Ошибки запросов к БД", "should", [f"sum(rate(db_queries_total{db_err_sel}[5m]))"]),
                Requirement(
                    "db_latency",
                    "Задержка запросов к БД p95",
                    "should",
                    [f"histogram_quantile(0.95, sum(rate(db_query_duration_seconds_bucket{{{job_label}=\"$job\"}}[5m])) by (le, operation))"],
                ),
            ]
        )

    if "business_orders" in modules:
        reqs.extend(
            [
                Requirement("orders_in_db", "Количество заказов в БД", "should", [f"max(orders_in_db{sel})"]),
                Requirement("orders_created", "Создание заказов", "should", [f"sum(rate(orders_created_total{sel}[5m]))"]),
                Requirement("orders_read", "Чтение заказов", "should", [f"sum(rate(orders_read_total{sel}[5m]))"]),
                Requirement("slow_requests", "Медленные запросы", "should", [f"sum(rate(slow_requests_total{sel}[5m]))"]),
            ]
        )

    if "postgres_exporter" in modules:
        reqs.extend(
            [
                Requirement("pg_connections", "Активные соединения", "must", [f"pg_stat_activity_count{sel}"]),
                Requirement(
                    "pg_transactions",
                    "Скорость транзакций",
                    "should",
                    [f"sum(rate(pg_stat_database_xact_commit{sel}[5m])) + sum(rate(pg_stat_database_xact_rollback{sel}[5m]))"],
                ),
                Requirement("pg_deadlocks", "Скорость дедлоков", "should", [f"sum(rate(pg_stat_database_deadlocks{sel}[5m]))"]),
            ]
        )

    if "container_metrics" in modules:
        reqs.extend(
            [
                Requirement("container_cpu", "Потребление CPU контейнером", "should", [f"sum(rate(container_cpu_usage_seconds_total{cadvisor_sel}[5m]))"]),
                Requirement("container_mem", "Потребление памяти контейнером", "should", [f"sum(container_memory_usage_bytes{cadvisor_sel})"]),
                Requirement("container_rx", "Входящий сетевой трафик контейнера", "should", [f"sum(rate(container_network_receive_bytes_total{cadvisor_sel}[5m]))"]),
                Requirement("container_tx", "Исходящий сетевой трафик контейнера", "should", [f"sum(rate(container_network_transmit_bytes_total{cadvisor_sel}[5m]))"]),
            ]
        )

    return _dedupe(reqs)


def host_requirements() -> list[Requirement]:
    return [
        Requirement("node_up", "Доступность node_exporter", "must", ['max(up{job="$job"})']),
        Requirement("node_cpu", "Загрузка CPU хоста", "should", ['100 * (1 - avg(rate(node_cpu_seconds_total{job="$job",mode="idle"}[5m])))']),
        Requirement("node_load", "Load average хоста", "should", ['node_load1{job="$job"}']),
        Requirement("node_mem", "Доступная память хоста", "should", ['node_memory_MemAvailable_bytes{job="$job"}']),
        Requirement("node_disk", "Свободное дисковое пространство хоста", "should", ['sum(node_filesystem_avail_bytes{job="$job",fstype!=""})']),
    ]