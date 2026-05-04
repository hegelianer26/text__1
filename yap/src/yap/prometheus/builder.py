from __future__ import annotations

from typing import Any

from yap.config.schema import ObservabilityConfig, ServiceConfig
from yap.inventory.compose import ComposeService
from yap.modules.registry import APP_SCRAPE_MODULES, compose_service_alerts, host_alerts


def _guess_exporter_service_name(service_name: str) -> str:
    return f"{service_name}-exporter"


def _service_requires_app_scrape(service_cfg: ServiceConfig) -> bool:
    return any(module in APP_SCRAPE_MODULES for module in service_cfg.modules)


def _infer_metrics_port(compose_service: ComposeService, service_cfg: ServiceConfig) -> int | None:
    if service_cfg.metrics_port is not None:
        return service_cfg.metrics_port
    if compose_service.ports:
        return compose_service.ports[0]
    return None


def _cadvisor_metric_relabel_configs() -> list[dict[str, Any]]:
    return [
        {
            "source_labels": ["container_label_com_docker_compose_service"],
            "target_label": "service",
            "regex": "(.+)",
            "replacement": "$1",
        }
    ]


def _build_alerts_rules(
    inventory: dict[str, ComposeService],
    cfg: ObservabilityConfig,
) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []

    for service_name, service_cfg in cfg.services.items():
        if service_name not in inventory:
            continue
        if service_cfg.disable_default_alerts:
            continue

        rules = compose_service_alerts(
            service_name=service_name,
            modules=service_cfg.modules,
            job_label=cfg.prometheus.job_label,
            alerts_cfg=cfg.alerts,
            container_metrics_enabled=cfg.telemetry.container_metrics,
            postgres_metrics_enabled=cfg.telemetry.postgres_metrics,
            enabled=cfg.alerts.enabled,
        )

        if not rules:
            continue

        groups.append(
            {
                "name": f"yap_{service_name}",
                "rules": [
                    {
                        "alert": rule.alert,
                        "expr": rule.expr,
                        "for": rule.duration,
                        "labels": rule.labels,
                        "annotations": rule.annotations,
                    }
                    for rule in rules
                ],
            }
        )

    if cfg.telemetry.host_metrics and cfg.alerts.enabled:
        rules = host_alerts(cfg.alerts, enabled=True)
        if rules:
            groups.append(
                {
                    "name": "yap_host",
                    "rules": [
                        {
                            "alert": rule.alert,
                            "expr": rule.expr,
                            "for": rule.duration,
                            "labels": rule.labels,
                            "annotations": rule.annotations,
                        }
                        for rule in rules
                    ],
                }
            )

    return {"groups": groups}


def build_prometheus_assets(
    inventory: dict[str, ComposeService],
    cfg: ObservabilityConfig,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    warnings: list[str] = []

    scrape_configs: list[dict[str, Any]] = []

    for service_name, service_cfg in cfg.services.items():
        if service_name not in inventory:
            continue

        compose_service = inventory[service_name]

        if _service_requires_app_scrape(service_cfg):
            port = _infer_metrics_port(compose_service, service_cfg)
            if port is None:
                warnings.append(
                    f"Service '{service_name}' requires app metrics scraping, but no port was found in docker-compose.yml and no metrics_port was set."
                )
            else:
                scrape_configs.append(
                    {
                        "job_name": service_name,
                        "metrics_path": service_cfg.metrics_path,
                        "static_configs": [{"targets": [f"{service_name}:{port}"]}],
                    }
                )

        if "postgres_exporter" in service_cfg.modules:
            if not cfg.telemetry.postgres_metrics:
                warnings.append(
                    f"Service '{service_name}' requested module 'postgres_exporter', but telemetry.postgres_metrics=false."
                )
            else:
                exporter_service = service_cfg.exporter_service or _guess_exporter_service_name(service_name)
                exporter_port = service_cfg.exporter_port or 9187

                if exporter_service not in inventory:
                    warnings.append(
                        f"Service '{service_name}' expects exporter '{exporter_service}', but it is not present in docker-compose.yml."
                    )
                scrape_configs.append(
                    {
                        "job_name": service_name,
                        "static_configs": [{"targets": [f"{exporter_service}:{exporter_port}"]}],
                    }
                )

        if "container_metrics" in service_cfg.modules and not cfg.telemetry.container_metrics:
            warnings.append(
                f"Service '{service_name}' requested module 'container_metrics', but telemetry.container_metrics=false."
            )

    if cfg.telemetry.host_metrics:
        if "node-exporter" not in inventory:
            warnings.append("telemetry.host_metrics=true, but service 'node-exporter' was not found in docker-compose.yml.")
        scrape_configs.append(
            {
                "job_name": "node",
                "static_configs": [{"targets": ["node-exporter:9100"]}],
            }
        )

    if cfg.telemetry.container_metrics:
        if "cadvisor" not in inventory:
            warnings.append("telemetry.container_metrics=true, but service 'cadvisor' was not found in docker-compose.yml.")
        scrape_configs.append(
            {
                "job_name": "cadvisor",
                "static_configs": [{"targets": ["cadvisor:8080"]}],
                "metric_relabel_configs": _cadvisor_metric_relabel_configs(),
            }
        )

    if cfg.telemetry.prometheus_self_metrics:
        scrape_configs.append(
            {
                "job_name": "prometheus",
                "static_configs": [{"targets": ["prometheus:9090"]}],
            }
        )

    prom_config: dict[str, Any] = {
        "global": {
            "scrape_interval": cfg.prometheus.scrape_interval,
            "evaluation_interval": cfg.prometheus.evaluation_interval,
        },
        "rule_files": ["alerts.yml"] if cfg.alerts.enabled else [],
        "scrape_configs": scrape_configs,
    }

    alerts_config = _build_alerts_rules(inventory, cfg)
    return prom_config, alerts_config, warnings