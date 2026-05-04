from __future__ import annotations

from pathlib import Path

import yaml

from yap.config.schema import ObservabilityConfig
from yap.inventory.compose import ComposeService
from yap.prometheus.builder import build_prometheus_assets


def write_prometheus_assets(
    inventory: dict[str, ComposeService],
    cfg: ObservabilityConfig,
    out_dir: Path,
) -> list[str]:
    prom_config, alerts_config, warnings = build_prometheus_assets(inventory, cfg)

    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "prometheus.yml").write_text(
        yaml.safe_dump(prom_config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (out_dir / "alerts.yml").write_text(
        yaml.safe_dump(alerts_config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    return warnings