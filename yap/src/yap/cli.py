from __future__ import annotations

from pathlib import Path

import typer

from yap.config.loader import load_observability_config, validate_service_mapping
from yap.dashboards.export import generate_dashboards
from yap.discovery.export import inspect_services, write_discovery_assets
from yap.inventory.compose import load_compose_inventory
from yap.prometheus.export import write_prometheus_assets
from yap.validation.report import write_plan_report

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def main() -> None:
    """YAP: observability bundle generator."""
    return


def _write_warnings(out_dir: Path, warnings: list[str]) -> None:
    if not warnings:
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "warnings.txt").write_text("\n".join(warnings) + "\n", encoding="utf-8")


def _common_load(compose: Path, config: Path):
    inventory = load_compose_inventory(compose)
    cfg = load_observability_config(config)
    warnings = validate_service_mapping(inventory, cfg)
    return inventory, cfg, warnings


@app.command()
def inspect(
    compose: Path = typer.Option(..., "--compose", "-c", exists=True, readable=True),
    out: Path = typer.Option(Path("discovered"), "--out", "-o"),
    metrics_path: str = typer.Option("/metrics", "--metrics-path"),
    timeout_seconds: float = typer.Option(3.0, "--timeout"),
) -> None:
    """
    Inspect published /metrics endpoints, save raw metric inventory and suggested observability config.
    """
    inventory = load_compose_inventory(compose)
    results = inspect_services(
        inventory=inventory,
        metrics_path=metrics_path,
        timeout_seconds=timeout_seconds,
    )
    write_discovery_assets(inventory, results, out)

    ok_count = sum(1 for result in results if result.status == "ok")
    typer.echo(f"Services in compose: {len(inventory)}")
    typer.echo(f"Inspectable metrics endpoints: {ok_count}")
    typer.echo(f"Outputs: {out}")


@app.command()
def dashboards(
    compose: Path = typer.Option(..., "--compose", "-c", exists=True, readable=True),
    config: Path = typer.Option(..., "--config", "-f", exists=True, readable=True),
    out: Path = typer.Option(Path("out"), "--out", "-o"),
) -> None:
    inventory, cfg, warnings = _common_load(compose, config)

    out.mkdir(parents=True, exist_ok=True)
    dashboards_dir = out / "dashboards"
    dashboards_dir.mkdir(parents=True, exist_ok=True)

    generated = generate_dashboards(inventory, cfg, dashboards_dir)
    write_plan_report(inventory, cfg, out)
    _write_warnings(out, warnings)

    typer.echo(f"Services in compose: {len(inventory)}")
    typer.echo(f"Dashboards generated: {generated}")
    if warnings:
        typer.echo(f"Warnings: {len(warnings)} (see {out / 'warnings.txt'})")
    typer.echo(f"Outputs: {out}")


@app.command()
def prometheus(
    compose: Path = typer.Option(..., "--compose", "-c", exists=True, readable=True),
    config: Path = typer.Option(..., "--config", "-f", exists=True, readable=True),
    out: Path = typer.Option(Path("out"), "--out", "-o"),
) -> None:
    inventory, cfg, warnings = _common_load(compose, config)

    out.mkdir(parents=True, exist_ok=True)
    prom_dir = out / "prometheus"
    prom_dir.mkdir(parents=True, exist_ok=True)

    prom_warnings = write_prometheus_assets(inventory, cfg, prom_dir)
    all_warnings = warnings + prom_warnings
    _write_warnings(out, all_warnings)

    typer.echo(f"Services in compose: {len(inventory)}")
    typer.echo(f"Prometheus assets: {prom_dir}")
    if all_warnings:
        typer.echo(f"Warnings: {len(all_warnings)} (see {out / 'warnings.txt'})")
    typer.echo(f"Outputs: {out}")


@app.command()
def bundle(
    compose: Path = typer.Option(..., "--compose", "-c", exists=True, readable=True),
    config: Path = typer.Option(..., "--config", "-f", exists=True, readable=True),
    out: Path = typer.Option(Path("out"), "--out", "-o"),
) -> None:
    inventory, cfg, warnings = _common_load(compose, config)

    out.mkdir(parents=True, exist_ok=True)
    dashboards_dir = out / "dashboards"
    prom_dir = out / "prometheus"

    dashboards_dir.mkdir(parents=True, exist_ok=True)
    prom_dir.mkdir(parents=True, exist_ok=True)

    generated = generate_dashboards(inventory, cfg, dashboards_dir)
    write_plan_report(inventory, cfg, out)
    prom_warnings = write_prometheus_assets(inventory, cfg, prom_dir)

    all_warnings = warnings + prom_warnings
    _write_warnings(out, all_warnings)

    typer.echo(f"Services in compose: {len(inventory)}")
    typer.echo(f"Dashboards generated: {generated}")
    typer.echo(f"Prometheus assets: {prom_dir}")
    if all_warnings:
        typer.echo(f"Warnings: {len(all_warnings)} (see {out / 'warnings.txt'})")
    typer.echo(f"Outputs: {out}")


if __name__ == "__main__":
    app()