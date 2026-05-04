from __future__ import annotations

from pathlib import Path

import yaml

from yap.config.schema import ObservabilityConfig
from yap.inventory.compose import ComposeService


def load_observability_config(path: str | Path) -> ObservabilityConfig:
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return ObservabilityConfig.model_validate(data)


def _guess_exporter_service_name(service_name: str) -> str:
    return f"{service_name}-exporter"


def _auto_managed_service_names(cfg: ObservabilityConfig) -> set[str]:
    auto_names = {"grafana", "prometheus"}

    if cfg.telemetry.host_metrics:
        auto_names.add("node-exporter")
    if cfg.telemetry.container_metrics:
        auto_names.add("cadvisor")

    for service_name, service_cfg in cfg.services.items():
        if "postgres_exporter" in service_cfg.modules:
            auto_names.add(service_cfg.exporter_service or _guess_exporter_service_name(service_name))

    auto_names.update(cfg.ignore_services)
    return auto_names


def validate_service_mapping(
    inventory: dict[str, ComposeService],
    cfg: ObservabilityConfig,
) -> list[str]:
    warnings: list[str] = []

    compose_services = set(inventory.keys())
    auto_names = _auto_managed_service_names(cfg)

    for service_name in cfg.services.keys():
        if service_name not in compose_services:
            warnings.append(
                f"Config maps service '{service_name}', but it's not present in docker-compose.yml."
            )

    for service_name in compose_services:
        if service_name not in cfg.services and service_name not in auto_names:
            warnings.append(
                f"Service '{service_name}' exists in docker-compose.yml but has no observability config; skipped."
            )

    return warnings