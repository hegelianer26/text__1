from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import yaml

from yap.discovery.parser import parse_metrics_text
from yap.discovery.suggest import (
    InspectionResult,
    build_inventory_document,
    build_suggested_config,
)
from yap.inventory.compose import ComposeService


def inspect_services(
    inventory: dict[str, ComposeService],
    metrics_path: str = "/metrics",
    timeout_seconds: float = 3.0,
) -> list[InspectionResult]:
    results: list[InspectionResult] = []

    for service_name, compose_service in inventory.items():
        if not compose_service.published_ports:
            results.append(
                InspectionResult(
                    service_name=service_name,
                    status="no_published_port",
                    metrics_endpoint=None,
                    container_port=compose_service.ports[0] if compose_service.ports else None,
                    published_port=None,
                    error="No published host port found in docker-compose.yml.",
                    metric_families=[],
                )
            )
            continue

        success_result: InspectionResult | None = None
        errors: list[str] = []

        for index, published_port in enumerate(compose_service.published_ports):
            container_port = compose_service.ports[index] if index < len(compose_service.ports) else None
            endpoint = f"http://127.0.0.1:{published_port}{metrics_path}"

            try:
                with urlopen(endpoint, timeout=timeout_seconds) as response:
                    body = response.read().decode("utf-8", errors="replace")
                    metric_families = parse_metrics_text(body)

                    success_result = InspectionResult(
                        service_name=service_name,
                        status="ok",
                        metrics_endpoint=endpoint,
                        container_port=container_port,
                        published_port=published_port,
                        error=None,
                        metric_families=metric_families,
                    )
                    break

            except HTTPError as exc:
                errors.append(f"{endpoint}: HTTP {exc.code}")
            except URLError as exc:
                errors.append(f"{endpoint}: {exc.reason}")
            except Exception as exc:
                errors.append(f"{endpoint}: {exc}")

        if success_result is not None:
            results.append(success_result)
        else:
            results.append(
                InspectionResult(
                    service_name=service_name,
                    status="inspect_failed",
                    metrics_endpoint=None,
                    container_port=compose_service.ports[0] if compose_service.ports else None,
                    published_port=compose_service.published_ports[0] if compose_service.published_ports else None,
                    error=" | ".join(errors[:5]) if errors else "Unknown inspection error.",
                    metric_families=[],
                )
            )

    return results


def write_discovery_assets(
    inventory: dict[str, ComposeService],
    results: list[InspectionResult],
    out_dir: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    inventory_doc = build_inventory_document(results)
    suggested_doc = build_suggested_config(inventory, results)

    (out_dir / "metrics.inventory.yaml").write_text(
        yaml.safe_dump(inventory_doc, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    (out_dir / "observability.suggested.yaml").write_text(
        yaml.safe_dump(suggested_doc, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )