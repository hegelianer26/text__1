from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ModuleName = Literal[
    "http_server",
    "http_client",
    "postgres_client",
    "postgres_exporter",
    "business_orders",
    "container_metrics",
]

PanelType = Literal["timeseries", "stat"]
MetricView = Literal["raw", "rate", "increase", "p95", "p99", "count_rate"]
AggregateOp = Literal["sum", "avg", "min", "max", "none"]


class PrometheusConfig(BaseModel):
    url: str = Field(..., description="Prometheus base URL")
    job_label: str = Field(default="job", description="Label for app metrics")
    scrape_interval: str = Field(default="5s")
    evaluation_interval: str = Field(default="5s")


class TelemetryConfig(BaseModel):
    host_metrics: bool = True
    container_metrics: bool = True
    postgres_metrics: bool = True
    prometheus_self_metrics: bool = True


class AlertsConfig(BaseModel):
    enabled: bool = True
    target_down_for: str = "2m"
    db_not_ready_for: str = "2m"
    http_error_rate_threshold: float = 0.05
    http_latency_p95_threshold_seconds: float = 0.75
    host_high_cpu_threshold_percent: float = 90.0
    host_high_cpu_for: str = "5m"


class DashboardPanelConfig(BaseModel):
    section: str = "Прикладные метрики"
    title: str
    expr: str
    panel_type: PanelType = "timeseries"


class DashboardMetricConfig(BaseModel):
    section: str = "Прикладные метрики"
    metric: str
    title: str | None = None
    view: MetricView = "raw"
    aggregate: AggregateOp = "sum"
    filters: dict[str, str] = Field(default_factory=dict)
    group_by: list[str] = Field(default_factory=list)
    panel_type: PanelType | None = None
    window: str = "5m"


class DashboardConfig(BaseModel):
    add_panels: list[DashboardPanelConfig] = Field(default_factory=list)
    add_metrics: list[DashboardMetricConfig] = Field(default_factory=list)


class ServiceConfig(BaseModel):
    modules: list[ModuleName] = Field(default_factory=list)

    metrics_port: int | None = None
    metrics_path: str = "/metrics"

    exporter_service: str | None = None
    exporter_port: int | None = None

    dashboard_title: str | None = None
    disable_default_alerts: bool = False
    dashboard: DashboardConfig | None = None


class ObservabilityConfig(BaseModel):
    version: int = 1
    prometheus: PrometheusConfig
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)
    services: dict[str, ServiceConfig] = Field(default_factory=dict)
    ignore_services: list[str] = Field(default_factory=list)