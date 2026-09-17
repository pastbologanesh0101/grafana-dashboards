"""
grafana_validate.py

Structural validation for Grafana dashboard JSON models.

This project cannot start a live Grafana instance in this environment
(no Docker daemon), so dashboards are validated *structurally*: required
schema fields are present, panel grid positions don't overlap, PromQL
query expressions are syntactically plausible, template variables used
in queries are actually declared, and datasource references are
consistent across panels. This is NOT a substitute for opening the
dashboards in a real Grafana instance -- see README.md.
"""
import json
import re

GRID_COLUMNS = 24

REQUIRED_TOP_LEVEL_FIELDS = [
    "title",
    "uid",
    "schemaVersion",
    "version",
    "panels",
    "templating",
    "time",
]

REQUIRED_PANEL_FIELDS = ["id", "type", "title", "gridPos", "datasource", "targets"]

VALID_PANEL_TYPES = {"timeseries", "stat", "gauge", "table", "bargauge", "piechart"}

# PromQL / Grafana template-variable reference, e.g. $job or ${job}
VAR_REF_RE = re.compile(r"\$\{?([a-zA-Z_][a-zA-Z0-9_]*)\}?")

# Loose "identifier-looking" token (metric name, label, function name, etc.)
IDENT_RE = re.compile(r"[a-zA-Z_:][a-zA-Z0-9_:]*")

# PromQL keywords / aggregation ops / function names that are NOT metric names.
# Used only to sanity-check that an expression contains at least one token
# that plausibly refers to a metric, not just keywords.
PROMQL_KEYWORDS = {
    "sum", "avg", "min", "max", "count", "count_values", "stddev", "stdvar",
    "topk", "bottomk", "quantile", "by", "without", "on", "ignoring",
    "group_left", "group_right", "rate", "irate", "increase",
    "histogram_quantile", "label_values", "le", "offset", "bool",
    "and", "or", "unless",
}


class ValidationError(AssertionError):
    """Raised when a dashboard fails a structural check."""


def load_dashboard(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_top_level_fields(dashboard):
    missing = [f for f in REQUIRED_TOP_LEVEL_FIELDS if f not in dashboard]
    if missing:
        raise ValidationError(f"Dashboard missing top-level fields: {missing}")
    if not isinstance(dashboard["panels"], list) or not dashboard["panels"]:
        raise ValidationError("Dashboard 'panels' must be a non-empty list")
    if "list" not in dashboard["templating"]:
        raise ValidationError("Dashboard 'templating' must have a 'list' key")
    return True


def check_panel_required_fields(panel):
    missing = [f for f in REQUIRED_PANEL_FIELDS if f not in panel]
    if missing:
        raise ValidationError(f"Panel {panel.get('title', '?')!r} missing fields: {missing}")

    if panel["type"] not in VALID_PANEL_TYPES:
        raise ValidationError(
            f"Panel {panel['title']!r} has unsupported type {panel['type']!r}"
        )

    gp = panel["gridPos"]
    for key in ("h", "w", "x", "y"):
        if key not in gp or not isinstance(gp[key], int) or gp[key] < 0:
            raise ValidationError(f"Panel {panel['title']!r} gridPos.{key} missing/invalid")
    if gp["w"] <= 0 or gp["h"] <= 0:
        raise ValidationError(f"Panel {panel['title']!r} gridPos has non-positive size")
    if gp["x"] + gp["w"] > GRID_COLUMNS:
        raise ValidationError(
            f"Panel {panel['title']!r} extends past the {GRID_COLUMNS}-column grid"
        )

    if not isinstance(panel["datasource"], dict) or "uid" not in panel["datasource"]:
        raise ValidationError(f"Panel {panel['title']!r} datasource must be a dict with 'uid'")

    if not panel["targets"]:
        raise ValidationError(f"Panel {panel['title']!r} has no targets")
    for t in panel["targets"]:
        if "expr" not in t or "refId" not in t:
            raise ValidationError(f"Panel {panel['title']!r} target missing 'expr'/'refId'")
    return True


def _rects_overlap(a, b):
    ax0, ax1 = a["x"], a["x"] + a["w"]
    ay0, ay1 = a["y"], a["y"] + a["h"]
    bx0, bx1 = b["x"], b["x"] + b["w"]
    by0, by1 = b["y"], b["y"] + b["h"]
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


def check_no_panel_overlap(panels):
    for i in range(len(panels)):
        for j in range(i + 1, len(panels)):
            gp_i, gp_j = panels[i]["gridPos"], panels[j]["gridPos"]
            if _rects_overlap(gp_i, gp_j):
                raise ValidationError(
                    f"Panels {panels[i]['title']!r} and {panels[j]['title']!r} overlap "
                    f"({gp_i} vs {gp_j})"
                )
    return True


def check_promql_expr(expr):
    if not expr or not expr.strip():
        raise ValidationError("Empty PromQL expression")
    if expr.count("(") != expr.count(")"):
        raise ValidationError(f"Unbalanced parentheses in expression: {expr!r}")
    if expr.count("{") != expr.count("}"):
        raise ValidationError(f"Unbalanced braces in expression: {expr!r}")

    tokens = IDENT_RE.findall(expr)
    if not tokens:
        raise ValidationError(f"No identifier-looking tokens found in expression: {expr!r}")

    metric_like = [t for t in tokens if t.lower() not in PROMQL_KEYWORDS]
    if not metric_like:
        raise ValidationError(f"No metric-name-like token found in expression: {expr!r}")
    return True


def check_panel_queries(panel):
    for target in panel["targets"]:
        check_promql_expr(target["expr"])
    return True


def get_declared_template_vars(dashboard):
    return {v["name"] for v in dashboard.get("templating", {}).get("list", [])}


def get_referenced_vars(expr):
    return set(VAR_REF_RE.findall(expr))


def check_template_vars_declared(dashboard):
    declared = get_declared_template_vars(dashboard)
    for panel in dashboard["panels"]:
        for target in panel["targets"]:
            referenced = get_referenced_vars(target["expr"])
            undeclared = referenced - declared
            if undeclared:
                raise ValidationError(
                    f"Panel {panel['title']!r} references undeclared template "
                    f"variable(s) {undeclared} (declared: {declared})"
                )
    return True


def check_datasource_consistency(dashboard):
    refs = set()
    for panel in dashboard["panels"]:
        ds = panel.get("datasource")
        if not isinstance(ds, dict):
            raise ValidationError(f"Panel {panel['title']!r} has no datasource dict")
        refs.add(json.dumps(ds, sort_keys=True))
    if len(refs) > 1:
        raise ValidationError(f"Inconsistent datasource references across panels: {refs}")
    return True


def validate_dashboard(dashboard):
    """Run every structural check against a dashboard dict. Raises
    ValidationError on the first failure; returns True if all pass."""
    check_top_level_fields(dashboard)
    panels = dashboard["panels"]
    for panel in panels:
        check_panel_required_fields(panel)
        check_panel_queries(panel)
    check_no_panel_overlap(panels)
    check_template_vars_declared(dashboard)
    check_datasource_consistency(dashboard)
    return True
