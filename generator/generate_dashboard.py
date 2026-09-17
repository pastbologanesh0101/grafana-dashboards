#!/usr/bin/env python3
"""
generate_dashboard.py

Programmatically builds a Grafana dashboard JSON model from a small,
declarative Python spec, instead of hand-copying dashboard JSON.

A "spec" is just:
  - a dashboard title + uid
  - a list of panel specs: {title, type, expr, unit, legend}
  - an optional list of template variables (beyond the default
    "$datasource" variable, which is always included)

The generator lays panels out automatically on Grafana's 24-column
grid (2 panels per row, non-overlapping by construction) and emits a
dashboard dict that conforms to the same schema validated by
lib/grafana_validate.py.

Usage:
    python generate_dashboard.py                       # print an example
    python generate_dashboard.py > dashboards/out.json  # save it
"""
import json
import sys

GRID_COLUMNS = 24
DEFAULT_PANEL_WIDTH = 12
DEFAULT_PANEL_HEIGHT = 8
VALID_PANEL_TYPES = {"timeseries", "stat", "gauge", "table", "bargauge", "piechart"}
REF_IDS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _datasource_ref(var_name="datasource"):
    return {"type": "prometheus", "uid": f"${{{var_name}}}"}


def _default_variables(extra_vars=None):
    variables = [
        {
            "name": "datasource",
            "type": "datasource",
            "label": "Datasource",
            "query": "prometheus",
            "current": {"text": "Prometheus", "value": "Prometheus"},
            "hide": 0,
        }
    ]
    if extra_vars:
        variables.extend(extra_vars)
    return variables


def make_query_variable(name, label, metric, datasource_var="datasource"):
    """Build a Grafana 'query' template variable backed by label_values()."""
    return {
        "name": name,
        "type": "query",
        "label": label,
        "datasource": {"type": "prometheus", "uid": f"${{{datasource_var}}}"},
        "query": f"label_values({metric}, {name})",
        "refresh": 2,
        "includeAll": False,
        "multi": False,
        "current": {"text": "", "value": ""},
        "options": [],
        "hide": 0,
    }


def _autolayout(index, width=DEFAULT_PANEL_WIDTH, height=DEFAULT_PANEL_HEIGHT):
    per_row = max(GRID_COLUMNS // width, 1)
    col = index % per_row
    row = index // per_row
    return {"h": height, "w": width, "x": col * width, "y": row * height}


def make_panel(panel_id, title, panel_type, exprs, index, unit="short", legend=None,
               width=DEFAULT_PANEL_WIDTH, height=DEFAULT_PANEL_HEIGHT):
    if panel_type not in VALID_PANEL_TYPES:
        raise ValueError(f"Unsupported panel type: {panel_type!r}")
    if isinstance(exprs, str):
        exprs = [exprs]
    if not exprs:
        raise ValueError(f"Panel {title!r} needs at least one PromQL expression")

    targets = []
    for i, expr in enumerate(exprs):
        target = {"expr": expr, "refId": REF_IDS[i]}
        if legend:
            target["legendFormat"] = legend
        if panel_type == "table":
            target["format"] = "table"
        targets.append(target)

    return {
        "id": panel_id,
        "type": panel_type,
        "title": title,
        "gridPos": _autolayout(index, width, height),
        "datasource": _datasource_ref(),
        "targets": targets,
        "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
        "options": {},
    }


def build_dashboard(title, uid, panel_specs, template_vars=None, tags=None, refresh="30s",
                     time_from="now-6h", time_to="now"):
    """
    panel_specs: list of dicts, each with keys:
        title (str, required)
        type  (str, required) - one of VALID_PANEL_TYPES
        expr  (str or list[str], required) - PromQL expression(s)
        unit  (str, optional, default "short")
        legend (str, optional) - legendFormat applied to each target
    template_vars: list of variable dicts (see make_query_variable), added
        on top of the always-present "$datasource" variable.
    """
    panels = []
    for i, spec in enumerate(panel_specs):
        for required_key in ("title", "type", "expr"):
            if required_key not in spec:
                raise ValueError(f"panel spec #{i} missing required key {required_key!r}")
        panels.append(
            make_panel(
                panel_id=i + 1,
                title=spec["title"],
                panel_type=spec["type"],
                exprs=spec["expr"],
                index=i,
                unit=spec.get("unit", "short"),
                legend=spec.get("legend"),
            )
        )

    return {
        "title": title,
        "uid": uid,
        "schemaVersion": 39,
        "version": 1,
        "tags": tags or [],
        "timezone": "browser",
        "refresh": refresh,
        "time": {"from": time_from, "to": time_to},
        "templating": {"list": _default_variables(template_vars)},
        "panels": panels,
    }


def example_spec():
    """A small self-contained spec used by the CLI entry point and by the
    test suite to prove generator output passes the same structural
    validation as the hand-written dashboards."""
    instance_var = make_query_variable("instance", "Instance", "up")
    panel_specs = [
        {
            "title": "Example Request Rate",
            "type": "timeseries",
            "expr": 'sum(rate(http_requests_total{instance="$instance"}[5m])) by (status)',
            "unit": "reqps",
            "legend": "{{status}}",
        },
        {
            "title": "Example Active Requests",
            "type": "stat",
            "expr": 'sum(http_requests_in_progress{instance="$instance"})',
            "unit": "short",
        },
        {
            "title": "Example Error Table",
            "type": "table",
            "expr": 'topk(5, sum(rate(http_requests_total{instance="$instance", status=~"5.."}[5m])) by (path))',
            "unit": "reqps",
        },
    ]
    return "Generated Example Dashboard", "generated-example", panel_specs, [instance_var]


def main():
    title, uid, panel_specs, template_vars = example_spec()
    dashboard = build_dashboard(title, uid, panel_specs, template_vars=template_vars)
    json.dump(dashboard, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
