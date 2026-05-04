from __future__ import annotations

from yap.config.schema import DashboardMetricConfig


def _quote_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _selector(job_label: str, filters: dict[str, str]) -> str:
    parts: list[str] = [f'{job_label}="$job"']
    for key in sorted(filters.keys()):
        parts.append(f'{key}={_quote_value(filters[key])}')
    return "{" + ",".join(parts) + "}"


def _aggregate(expr: str, aggregate: str, group_by: list[str], default_when_grouped: str = "sum") -> str:
    if group_by and aggregate == "none":
        aggregate = default_when_grouped

    if aggregate == "none":
        return expr

    if group_by:
        labels = ", ".join(group_by)
        return f"{aggregate} by ({labels}) ({expr})"

    return f"{aggregate}({expr})"


def default_panel_type(metric_cfg: DashboardMetricConfig) -> str:
    if metric_cfg.panel_type is not None:
        return metric_cfg.panel_type

    if metric_cfg.view == "raw" and not metric_cfg.group_by:
        return "stat"

    return "timeseries"


def default_title(metric_cfg: DashboardMetricConfig) -> str:
    if metric_cfg.title:
        return metric_cfg.title

    base = metric_cfg.metric
    if metric_cfg.view == "rate":
        return f"{base} rate"
    if metric_cfg.view == "increase":
        return f"{base} increase"
    if metric_cfg.view == "p95":
        return f"{base} p95"
    if metric_cfg.view == "p99":
        return f"{base} p99"
    if metric_cfg.view == "count_rate":
        return f"{base} count rate"
    return base


def build_promql(metric_cfg: DashboardMetricConfig, job_label: str) -> str:
    sel = _selector(job_label, metric_cfg.filters)
    window = metric_cfg.window
    aggregate = metric_cfg.aggregate
    group_by = list(metric_cfg.group_by)

    if metric_cfg.view == "raw":
        expr = f"{metric_cfg.metric}{sel}"
        return _aggregate(expr, aggregate, group_by)

    if metric_cfg.view == "rate":
        expr = f"rate({metric_cfg.metric}{sel}[{window}])"
        return _aggregate(expr, aggregate, group_by)

    if metric_cfg.view == "increase":
        expr = f"increase({metric_cfg.metric}{sel}[{window}])"
        return _aggregate(expr, aggregate, group_by)

    if metric_cfg.view == "count_rate":
        expr = f"rate({metric_cfg.metric}_count{sel}[{window}])"
        return _aggregate(expr, aggregate, group_by)

    if metric_cfg.view in {"p95", "p99"}:
        q = "0.95" if metric_cfg.view == "p95" else "0.99"
        rate_expr = f"rate({metric_cfg.metric}_bucket{sel}[{window}])"

        agg = aggregate if aggregate != "none" else "sum"
        group_labels = ["le"] + group_by
        labels = ", ".join(group_labels)
        aggregated = f"{agg} by ({labels}) ({rate_expr})"
        return f"histogram_quantile({q}, {aggregated})"

    raise ValueError(f"Unsupported metric view: {metric_cfg.view}")