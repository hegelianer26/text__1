from __future__ import annotations

import json
import re
from collections import OrderedDict
from pathlib import Path

from yap.config.schema import DashboardMetricConfig, DashboardPanelConfig, ObservabilityConfig
from yap.dashboards.builder import build_dashboard
from yap.dashboards.promql import build_promql, default_panel_type, default_title
from yap.inventory.compose import ComposeService
from yap.modules.base import PanelSpec
from yap.modules.registry import compose_service_sections, host_sections


def make_dashboard_uid(name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-").lower()
    return f"yap-{normalized}"[:40]


def _append_custom_items(
    base_sections: list[tuple[str, list[PanelSpec]]],
    add_panels: list[DashboardPanelConfig],
    add_metrics: list[DashboardMetricConfig],
    job_label: str,
) -> list[tuple[str, list[PanelSpec]]]:
    sections_map: OrderedDict[str, list[PanelSpec]] = OrderedDict()

    for section_name, panels in base_sections:
        sections_map[section_name] = list(panels)

    for panel in add_panels:
        sections_map.setdefault(panel.section, [])
        sections_map[panel.section].append(
            PanelSpec(
                title=panel.title,
                expr=panel.expr,
                panel_type=panel.panel_type,
            )
        )

    for metric_cfg in add_metrics:
        sections_map.setdefault(metric_cfg.section, [])
        sections_map[metric_cfg.section].append(
            PanelSpec(
                title=default_title(metric_cfg),
                expr=build_promql(metric_cfg, job_label),
                panel_type=default_panel_type(metric_cfg),
            )
        )

    return [(section_name, panels) for section_name, panels in sections_map.items() if panels]


def generate_dashboards(
    inventory: dict[str, ComposeService],
    cfg: ObservabilityConfig,
    out_dir: Path,
) -> int:
    count = 0

    for service_name, service_cfg in cfg.services.items():
        if service_name not in inventory:
            continue

        title = service_cfg.dashboard_title or f"{service_name} — наблюдаемость"
        sections = compose_service_sections(
            service_cfg.modules,
            job_label=cfg.prometheus.job_label,
            container_metrics_enabled=cfg.telemetry.container_metrics,
            postgres_metrics_enabled=cfg.telemetry.postgres_metrics,
        )

        if service_cfg.dashboard:
            sections = _append_custom_items(
                base_sections=sections,
                add_panels=service_cfg.dashboard.add_panels,
                add_metrics=service_cfg.dashboard.add_metrics,
                job_label=cfg.prometheus.job_label,
            )

        tags = ["yap", "mvp"] + sorted(set(service_cfg.modules))

        dash = build_dashboard(
            title=title,
            sections=sections,
            default_job=service_name,
            uid=make_dashboard_uid(service_name),
            tags=tags,
        )

        (out_dir / f"{service_name}.json").write_text(
            json.dumps(dash, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        count += 1

    if cfg.telemetry.host_metrics:
        dash = build_dashboard(
            title="host — системная наблюдаемость",
            sections=host_sections(),
            default_job="node",
            uid=make_dashboard_uid("host"),
            tags=["yap", "mvp", "host_metrics"],
        )
        (out_dir / "host.json").write_text(
            json.dumps(dash, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        count += 1

    return count