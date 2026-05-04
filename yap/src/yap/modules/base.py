from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class PanelSpec:
    title: str
    expr: str
    panel_type: str = "timeseries"


@dataclass(frozen=True)
class RequirementSpec:
    id: str
    title: str
    level: str
    promql_templates: list[str]
    note: str | None = None


@dataclass(frozen=True)
class AlertRuleSpec:
    alert: str
    expr: str
    duration: str = "5m"
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)


class Module(Protocol):
    name: str

    def dashboard_sections(self, job_label: str) -> dict[str, list[PanelSpec]]:
        ...

    def requirements(self, job_label: str) -> list[RequirementSpec]:
        ...

    def alerts(
        self,
        job_label: str,
        service_name: str,
        alerts_cfg,
    ) -> list[AlertRuleSpec]:
        ...

    def telemetry_needs(self) -> set[str]:
        ...