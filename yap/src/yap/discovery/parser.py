from __future__ import annotations

from dataclasses import dataclass, field
import re


HELP_RE = re.compile(r"^#\s*HELP\s+([a-zA-Z_:][a-zA-Z0-9_:]*)\s+(.*)$")
TYPE_RE = re.compile(r"^#\s*TYPE\s+([a-zA-Z_:][a-zA-Z0-9_:]*)\s+([a-zA-Z]+)\s*$")
SAMPLE_RE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{([^}]*)\})?\s+')
LABEL_VALUE_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:\\.|[^"\\])*)"')


@dataclass(frozen=True)
class MetricFamilyInfo:
    name: str
    type: str
    labels: list[str]
    help: str | None = None
    parts: list[str] | None = None
    sample_count: int = 0
    label_values_sample: dict[str, list[str]] = field(default_factory=dict)


def _unescape_label_value(value: str) -> str:
    return (
        value.replace(r"\\", "\\")
        .replace(r"\"", '"')
        .replace(r"\n", "\n")
        .replace(r"\t", "\t")
    )


def _family_name_and_part(sample_name: str, type_by_name: dict[str, str]) -> tuple[str, str | None]:
    suffixes = ("bucket", "sum", "count", "created")
    for suffix in suffixes:
        marker = f"_{suffix}"
        if sample_name.endswith(marker):
            base = sample_name[: -len(marker)]
            base_type = type_by_name.get(base)
            if base_type in {"histogram", "summary", "counter"}:
                return base, suffix
    return sample_name, None


def parse_metrics_text(text: str, max_label_values_per_label: int = 5) -> list[MetricFamilyInfo]:
    help_by_name: dict[str, str] = {}
    type_by_name: dict[str, str] = {}
    families: dict[str, dict[str, object]] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        help_match = HELP_RE.match(line)
        if help_match:
            metric_name, help_text = help_match.groups()
            help_by_name[metric_name] = help_text
            continue

        type_match = TYPE_RE.match(line)
        if type_match:
            metric_name, metric_type = type_match.groups()
            type_by_name[metric_name] = metric_type
            continue

        if line.startswith("#"):
            continue

        sample_match = SAMPLE_RE.match(line)
        if not sample_match:
            continue

        sample_name, labels_blob = sample_match.groups()
        family_name, part = _family_name_and_part(sample_name, type_by_name)

        family = families.setdefault(
            family_name,
            {
                "name": family_name,
                "type": type_by_name.get(family_name, "untyped"),
                "labels": set(),
                "help": help_by_name.get(family_name),
                "parts": set(),
                "sample_count": 0,
                "label_values_sample": {},
            },
        )

        if labels_blob:
            for label_name, raw_value in LABEL_VALUE_RE.findall(labels_blob):
                family["labels"].add(label_name)

                label_values_sample: dict[str, list[str]] = family["label_values_sample"]  # type: ignore[assignment]
                values = label_values_sample.setdefault(label_name, [])
                value = _unescape_label_value(raw_value)
                if value not in values and len(values) < max_label_values_per_label:
                    values.append(value)

        if part:
            family["parts"].add(part)

        family["sample_count"] = int(family["sample_count"]) + 1

    result: list[MetricFamilyInfo] = []
    for name in sorted(families.keys()):
        family = families[name]
        parts = sorted(family["parts"])
        label_values_sample = {
            label_name: values
            for label_name, values in sorted(family["label_values_sample"].items())
            if values
        }

        result.append(
            MetricFamilyInfo(
                name=name,
                type=str(family["type"]),
                labels=sorted(family["labels"]),
                help=str(family["help"]) if family["help"] else None,
                parts=parts if parts else None,
                sample_count=int(family["sample_count"]),
                label_values_sample=label_values_sample,
            )
        )

    return result