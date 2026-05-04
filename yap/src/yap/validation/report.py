from __future__ import annotations

from pathlib import Path

from yap.config.schema import ObservabilityConfig
from yap.inventory.compose import ComposeService
from yap.modules.registry import (
    compose_service_alerts,
    compose_service_requirements,
    host_alerts,
    host_requirements,
)


def write_plan_report(
    inventory: dict[str, ComposeService],
    cfg: ObservabilityConfig,
    out_dir: Path,
) -> None:
    lines: list[str] = []
    lines.append("# План требований к наблюдаемости")
    lines.append("")
    lines.append("Сгенерировано автоматически по docker-compose.yml и observability.yaml.")
    lines.append("")

    for service_name, service_cfg in cfg.services.items():
        if service_name not in inventory:
            continue

        lines.append(f"## {service_name}")
        lines.append("")
        lines.append(f"- Модули: `{', '.join(service_cfg.modules) if service_cfg.modules else 'none'}`")
        lines.append("")

        requirements = compose_service_requirements(
            service_cfg.modules,
            job_label=cfg.prometheus.job_label,
            container_metrics_enabled=cfg.telemetry.container_metrics,
            postgres_metrics_enabled=cfg.telemetry.postgres_metrics,
        )

        if requirements:
            lines.append("### Метрики и требования")
            lines.append("")
            for req in requirements:
                level_text = "ОБЯЗАТЕЛЬНО" if req.level == "must" else "РЕКОМЕНДУЕТСЯ"
                lines.append(f"- **{req.title}** ({level_text})")
                for promql in req.promql_templates:
                    lines.append(f"  - `{promql.replace('$job', service_name)}`")
                if req.note:
                    lines.append(f"  - примечание: {req.note}")
            lines.append("")

        if cfg.alerts.enabled and not service_cfg.disable_default_alerts:
            alerts = compose_service_alerts(
                service_name=service_name,
                modules=service_cfg.modules,
                job_label=cfg.prometheus.job_label,
                alerts_cfg=cfg.alerts,
                container_metrics_enabled=cfg.telemetry.container_metrics,
                postgres_metrics_enabled=cfg.telemetry.postgres_metrics,
                enabled=True,
            )
            if alerts:
                lines.append("### Базовые алерты")
                lines.append("")
                for alert in alerts:
                    lines.append(f"- **{alert.alert}**")
                    lines.append(f"  - `expr: {alert.expr}`")
                    lines.append(f"  - `for: {alert.duration}`")
                lines.append("")

    if cfg.telemetry.host_metrics:
        lines.append("## host")
        lines.append("")
        lines.append("- Модули: `host_metrics`")
        lines.append("")

        lines.append("### Метрики и требования")
        lines.append("")
        for req in host_requirements():
            level_text = "ОБЯЗАТЕЛЬНО" if req.level == "must" else "РЕКОМЕНДУЕТСЯ"
            lines.append(f"- **{req.title}** ({level_text})")
            for promql in req.promql_templates:
                lines.append(f"  - `{promql.replace('$job', 'node')}`")
        lines.append("")

        if cfg.alerts.enabled:
            lines.append("### Базовые алерты")
            lines.append("")
            for alert in host_alerts(cfg.alerts, enabled=True):
                lines.append(f"- **{alert.alert}**")
                lines.append(f"  - `expr: {alert.expr}`")
                lines.append(f"  - `for: {alert.duration}`")
            lines.append("")

    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")