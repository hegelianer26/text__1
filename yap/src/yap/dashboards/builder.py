from __future__ import annotations

from typing import Any

from yap.modules.base import PanelSpec


def dashboard_skeleton(title: str, uid: str | None = None, tags: list[str] | None = None) -> dict[str, Any]:
    dash: dict[str, Any] = {
        "title": title,
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "refresh": "30s",
        "editable": True,
        "tags": tags or ["yap"],
        "panels": [],
        "templating": {"list": []},
        "time": {"from": "now-6h", "to": "now"},
    }
    if uid:
        dash["uid"] = uid
    return dash


def add_constant_variable(dash: dict[str, Any], name: str, value: str, label: str | None = None) -> None:
    dash["templating"]["list"].append(
        {
            "name": name,
            "type": "constant",
            "label": label or name,
            "query": value,
            "current": {"text": value, "value": value},
            "hide": 0,
        }
    )


def make_panel(panel_id: int, y: int, x: int, w: int, h: int, spec: PanelSpec) -> dict[str, Any]:
    panel: dict[str, Any] = {
        "id": panel_id,
        "type": spec.panel_type,
        "title": spec.title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "targets": [{"refId": "A", "expr": spec.expr}],
        "options": {},
        "fieldConfig": {"defaults": {}, "overrides": []},
    }

    if spec.panel_type == "stat":
        panel["options"] = {
            "reduceOptions": {
                "calcs": ["lastNotNull"],
                "fields": "",
                "values": False,
            }
        }

    return panel


def _layout_widths(count: int) -> list[int]:
    if count <= 0:
        return []
    if count == 1:
        return [24]

    widths: list[int] = []
    remaining = count
    while remaining > 0:
        if remaining == 1:
            widths.append(24)
            remaining -= 1
        else:
            widths.extend([12, 12])
            remaining -= 2
    return widths


def build_dashboard(
    title: str,
    sections: list[tuple[str, list[PanelSpec]]],
    default_job: str | None = None,
    uid: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    dash = dashboard_skeleton(title=title, uid=uid, tags=tags)

    if default_job is not None:
        add_constant_variable(dash, name="job", value=default_job, label="job")

    panel_id = 1
    y = 0

    for section_title, specs in sections:
        if not specs:
            continue

        dash["panels"].append(
            {
                "id": panel_id,
                "type": "row",
                "title": section_title,
                "gridPos": {"x": 0, "y": y, "w": 24, "h": 1},
            }
        )
        panel_id += 1
        y += 1

        widths = _layout_widths(len(specs))
        x = 0
        h = 8

        for spec, width in zip(specs, widths):
            dash["panels"].append(make_panel(panel_id, y, x, width, h, spec))
            panel_id += 1

            if width == 24:
                x = 0
                y += h
            else:
                x += width
                if x >= 24:
                    x = 0
                    y += h

        if x != 0:
            y += h

    return dash