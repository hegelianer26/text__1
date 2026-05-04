from __future__ import annotations

from yap.dashboards.builder import PanelSpec

APP_METRICS_MODULES = {
    "http_server",
    "http_client",
    "postgres_client",
    "business_orders",
}


def service_sections_for_modules(
    modules: list[str],
    job_label: str = "job",
) -> list[tuple[str, list[PanelSpec]]]:
    mods = set(modules)

    sel = f'{{{job_label}="$job"}}'
    err_sel = f'{{{job_label}="$job",status=~"5.."}}'
    outbound_err_sel = f'{{{job_label}="$job",status=~"5..|error"}}'
    db_ok_sel = f'{{{job_label}="$job",status="ok"}}'
    db_err_sel = f'{{{job_label}="$job",status="error"}}'
    cadvisor_sel = '{job="cadvisor",service="$job"}'

    overview: list[PanelSpec] = []
    app: list[PanelSpec] = []
    container: list[PanelSpec] = []

    if "http_server" in mods or "postgres_exporter" in mods or "postgres_client" in mods or "business_orders" in mods:
        overview.append(PanelSpec("up", f"max(up{sel})", "stat"))

    if "http_server" in mods:
        app.extend(
            [
                PanelSpec("http requests/s", f"sum(rate(http_requests_total{sel}[5m]))"),
                PanelSpec("http errors/s (5xx)", f"sum(rate(http_requests_total{err_sel}[5m]))"),
                PanelSpec(
                    "http latency p95",
                    f"histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{sel}[5m])) by (le))",
                ),
                PanelSpec("inflight requests", f"sum(http_inflight_requests{sel})"),
                PanelSpec("response bytes/s", f"sum(rate(http_response_bytes_total{sel}[5m]))"),
            ]
        )

    if "http_client" in mods:
        overview.append(PanelSpec("downstream up", f"min(downstream_up{sel})", "stat"))
        app.extend(
            [
                PanelSpec("outbound requests/s", f"sum(rate(outbound_http_requests_total{sel}[5m]))"),
                PanelSpec("outbound errors/s", f"sum(rate(outbound_http_requests_total{outbound_err_sel}[5m]))"),
                PanelSpec(
                    "outbound latency p95",
                    f"histogram_quantile(0.95, sum(rate(outbound_http_request_duration_seconds_bucket{sel}[5m])) by (le))",
                ),
                PanelSpec("outbound response bytes/s", f"sum(rate(outbound_http_response_bytes_total{sel}[5m]))"),
                PanelSpec("proxy actions/s", f"sum(rate(proxy_actions_total{sel}[5m]))"),
            ]
        )

    if "postgres_client" in mods:
        overview.append(PanelSpec("db ready", f"max(db_ready{sel})", "stat"))
        app.extend(
            [
                PanelSpec("db queries/s", f"sum(rate(db_queries_total{db_ok_sel}[5m]))"),
                PanelSpec("db errors/s", f"sum(rate(db_queries_total{db_err_sel}[5m]))"),
                PanelSpec(
                    "db latency p95",
                    f"histogram_quantile(0.95, sum(rate(db_query_duration_seconds_bucket{{{job_label}=\"$job\"}}[5m])) by (le, operation))",
                ),
            ]
        )

    if "business_orders" in mods:
        overview.extend(
            [
                PanelSpec("orders in db", f"max(orders_in_db{sel})", "stat"),
                PanelSpec("quantity sum", f"max(orders_quantity_sum{sel})", "stat"),
            ]
        )
        app.extend(
            [
                PanelSpec("orders created/s", f"sum(rate(orders_created_total{sel}[5m]))"),
                PanelSpec("orders read/s", f"sum(rate(orders_read_total{sel}[5m]))"),
                PanelSpec("summary requests/s", f"sum(rate(orders_summary_requests_total{sel}[5m]))"),
                PanelSpec("slow requests/s", f"sum(rate(slow_requests_total{sel}[5m]))"),
                PanelSpec("intentional errors/s", f"sum(rate(intentional_errors_total{sel}[5m]))"),
            ]
        )

    if "postgres_exporter" in mods:
        overview.append(PanelSpec("connections", f"pg_stat_activity_count{sel}", "stat"))
        app.extend(
            [
                PanelSpec(
                    "transactions/s",
                    f"sum(rate(pg_stat_database_xact_commit{sel}[5m])) + sum(rate(pg_stat_database_xact_rollback{sel}[5m]))",
                ),
                PanelSpec("deadlocks/s", f"sum(rate(pg_stat_database_deadlocks{sel}[5m]))"),
                PanelSpec(
                    "cache hit ratio",
                    f"sum(rate(pg_stat_database_blks_hit{sel}[5m])) / (sum(rate(pg_stat_database_blks_hit{sel}[5m])) + sum(rate(pg_stat_database_blks_read{sel}[5m])))",
                ),
            ]
        )

    if "container_metrics" in mods:
        container.extend(
            [
                PanelSpec("container cpu usage", f"sum(rate(container_cpu_usage_seconds_total{cadvisor_sel}[5m]))"),
                PanelSpec("container memory usage", f"sum(container_memory_usage_bytes{cadvisor_sel})"),
                PanelSpec("container net rx/s", f"sum(rate(container_network_receive_bytes_total{cadvisor_sel}[5m]))"),
                PanelSpec("container net tx/s", f"sum(rate(container_network_transmit_bytes_total{cadvisor_sel}[5m]))"),
            ]
        )

    return [
        ("Обзор", overview),
        ("Прикладные метрики", app),
        ("Контейнерные метрики (cAdvisor)", container),
    ]


def host_dashboard_sections() -> list[tuple[str, list[PanelSpec]]]:
    overview = [
        PanelSpec("node up", 'max(up{job="$job"})', "stat"),
    ]
    panels = [
        PanelSpec("cpu busy %", '100 * (1 - avg(rate(node_cpu_seconds_total{job="$job",mode="idle"}[5m])))'),
        PanelSpec("load1", 'node_load1{job="$job"}'),
        PanelSpec("mem available", 'node_memory_MemAvailable_bytes{job="$job"}'),
        PanelSpec("disk free total", 'sum(node_filesystem_avail_bytes{job="$job",fstype!=""})'),
        PanelSpec("net rx/s", 'sum(rate(node_network_receive_bytes_total{job="$job"}[5m]))'),
        PanelSpec("net tx/s", 'sum(rate(node_network_transmit_bytes_total{job="$job"}[5m]))'),
    ]
    return [
        ("Обзор", overview),
        ("Системные метрики хоста (node_exporter)", panels),
    ]