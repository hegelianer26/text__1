from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ComposeService:
    name: str
    ports: list[int]           # container/target ports
    published_ports: list[int] # host/published ports
    raw: dict[str, Any]


def _parse_port_entry(entry: Any) -> tuple[int | None, int | None]:
    """
    Returns (published_port, target_port)
    """
    if isinstance(entry, int):
        return None, entry

    if isinstance(entry, str):
        value = entry.split("/")[0].strip()

        if ":" not in value:
            return None, int(value) if value.isdigit() else (None, None)

        parts = value.split(":")
        if len(parts) == 2:
            published, target = parts
        else:
            # host_ip:published:target
            published, target = parts[-2], parts[-1]

        published_port = int(published) if published.isdigit() else None
        target_port = int(target) if target.isdigit() else None
        return published_port, target_port

    if isinstance(entry, dict):
        published = entry.get("published")
        target = entry.get("target")

        published_port = int(published) if isinstance(published, int) or (isinstance(published, str) and published.isdigit()) else None
        target_port = int(target) if isinstance(target, int) or (isinstance(target, str) and target.isdigit()) else None
        return published_port, target_port

    return None, None


def _extract_ports(service_def: dict[str, Any]) -> tuple[list[int], list[int]]:
    target_ports: list[int] = []
    published_ports: list[int] = []

    for entry in service_def.get("ports", []) or []:
        published, target = _parse_port_entry(entry)
        if target is not None and target not in target_ports:
            target_ports.append(target)
        if published is not None and published not in published_ports:
            published_ports.append(published)

    for entry in service_def.get("expose", []) or []:
        _, target = _parse_port_entry(entry)
        if target is not None and target not in target_ports:
            target_ports.append(target)

    return target_ports, published_ports


def load_compose_inventory(compose_path: str | Path) -> dict[str, ComposeService]:
    path = Path(compose_path)
    doc: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    services = doc.get("services")
    if not isinstance(services, dict) or not services:
        raise ValueError("docker-compose.yml has no 'services' section (or it's empty).")

    inventory: dict[str, ComposeService] = {}
    for service_name, service_def in services.items():
        if not isinstance(service_def, dict):
            service_def = {}

        target_ports, published_ports = _extract_ports(service_def)

        inventory[service_name] = ComposeService(
            name=service_name,
            ports=target_ports,
            published_ports=published_ports,
            raw=service_def,
        )

    return inventory