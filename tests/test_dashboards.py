"""
Structural tests for the bundled dashboard JSON files.

These tests do NOT start Grafana (no Docker daemon in this environment).
They validate the dashboard JSON models against the Grafana schema
structurally: required fields, valid panel types/grid positions, no
panel overlap, syntactically plausible PromQL, template-variable
declarations, and datasource consistency. See README.md.
"""
import json

import pytest

from lib.grafana_validate import (
    ValidationError,
    check_datasource_consistency,
    check_no_panel_overlap,
    check_panel_queries,
    check_panel_required_fields,
    check_promql_expr,
    check_template_vars_declared,
    check_top_level_fields,
    get_declared_template_vars,
    get_referenced_vars,
    load_dashboard,
    validate_dashboard,
)
from tests.conftest import DASHBOARDS_DIR

DASHBOARD_FILES = sorted(DASHBOARDS_DIR.glob("*.json"))
DASHBOARD_IDS = [p.stem for p in DASHBOARD_FILES]

assert DASHBOARD_FILES, "No dashboard JSON files found in dashboards/"


@pytest.fixture(params=DASHBOARD_FILES, ids=DASHBOARD_IDS)
def dashboard_path(request):
    return request.param


@pytest.fixture
def dashboard(dashboard_path):
    return load_dashboard(dashboard_path)


def test_dashboard_is_valid_json(dashboard_path):
    with open(dashboard_path) as f:
        data = json.load(f)
    assert isinstance(data, dict)


def test_dashboard_has_required_top_level_fields(dashboard):
    assert check_top_level_fields(dashboard) is True
    assert dashboard["title"]
    assert dashboard["uid"]


def test_dashboard_panels_have_required_fields(dashboard):
    for panel in dashboard["panels"]:
        assert check_panel_required_fields(panel) is True


def test_dashboard_panels_do_not_overlap(dashboard):
    assert check_no_panel_overlap(dashboard["panels"]) is True


def test_dashboard_panel_queries_are_valid_promql(dashboard):
    for panel in dashboard["panels"]:
        assert check_panel_queries(panel) is True


def test_dashboard_template_vars_are_declared(dashboard):
    assert check_template_vars_declared(dashboard) is True


def test_dashboard_datasource_references_are_consistent(dashboard):
    assert check_datasource_consistency(dashboard) is True


def test_dashboard_passes_full_validation(dashboard):
    assert validate_dashboard(dashboard) is True


def test_dashboard_has_at_least_one_template_variable(dashboard):
    declared = get_declared_template_vars(dashboard)
    # every bundled dashboard should have $datasource plus at least one
    # query-based variable (job/instance) actually used in a query
    assert len(declared) >= 2


def test_dashboard_variables_are_actually_referenced_somewhere(dashboard):
    declared = get_declared_template_vars(dashboard) - {"datasource"}
    used = set()
    for panel in dashboard["panels"]:
        for target in panel["targets"]:
            used |= get_referenced_vars(target["expr"])
    # at least one non-datasource declared variable must show up in a query
    assert declared & used, f"declared vars {declared} never used in any query ({used})"


class TestPromqlExprHelperDirectly:
    """Direct unit tests of the PromQL structural checker (not tied to a
    specific bundled dashboard file)."""

    def test_rejects_empty_expression(self):
        with pytest.raises(ValidationError):
            check_promql_expr("")

    def test_rejects_unbalanced_parens(self):
        with pytest.raises(ValidationError):
            check_promql_expr("sum(rate(http_requests_total[5m])")

    def test_rejects_unbalanced_braces(self):
        with pytest.raises(ValidationError):
            check_promql_expr('http_requests_total{job="api"')

    def test_rejects_pure_keyword_expression(self):
        with pytest.raises(ValidationError):
            check_promql_expr("sum by rate")

    def test_accepts_well_formed_histogram_quantile(self):
        expr = 'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job="$job"}[5m])) by (le))'
        assert check_promql_expr(expr) is True


def test_panel_type_variety_across_collection():
    """Across the whole bundled collection we should see the required mix
    of panel types: timeseries, stat, gauge, and table."""
    seen_types = set()
    for path in DASHBOARD_FILES:
        dashboard = load_dashboard(path)
        for panel in dashboard["panels"]:
            seen_types.add(panel["type"])
    required = {"timeseries", "stat", "gauge", "table"}
    assert required.issubset(seen_types), f"missing panel types: {required - seen_types}"


def test_all_dashboard_uids_are_unique():
    uids = [load_dashboard(p)["uid"] for p in DASHBOARD_FILES]
    assert len(uids) == len(set(uids))
