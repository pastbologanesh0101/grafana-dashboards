"""
Tests for generator/generate_dashboard.py: proves the generator produces
dashboard JSON that itself passes the same structural validation used
for the hand-written bundled dashboards.
"""
import pytest

from generator.generate_dashboard import (
    build_dashboard,
    example_spec,
    make_panel,
    make_query_variable,
)
from lib.grafana_validate import ValidationError, validate_dashboard


def test_example_spec_produces_valid_dashboard():
    title, uid, panel_specs, template_vars = example_spec()
    dashboard = build_dashboard(title, uid, panel_specs, template_vars=template_vars)
    assert validate_dashboard(dashboard) is True


def test_generated_dashboard_has_expected_title_and_uid():
    title, uid, panel_specs, template_vars = example_spec()
    dashboard = build_dashboard(title, uid, panel_specs, template_vars=template_vars)
    assert dashboard["title"] == title
    assert dashboard["uid"] == uid


def test_autolayout_produces_non_overlapping_grid_for_many_panels():
    panel_specs = [
        {
            "title": f"Panel {i}",
            "type": "timeseries",
            "expr": f"sum(rate(custom_metric_{i}_total[5m]))",
        }
        for i in range(7)
    ]
    dashboard = build_dashboard("Stress Test", "stress-test", panel_specs)
    assert validate_dashboard(dashboard) is True
    assert len(dashboard["panels"]) == 7


def test_build_dashboard_rejects_panel_spec_missing_type():
    with pytest.raises(ValueError):
        build_dashboard(
            "Broken", "broken", [{"title": "No type", "expr": "up"}]
        )


def test_make_panel_rejects_unsupported_panel_type():
    with pytest.raises(ValueError):
        make_panel(1, "Bad Panel", "pie3d-legacy", "up", index=0)


def test_make_query_variable_shape():
    var = make_query_variable("job", "Job", "http_requests_total")
    assert var["name"] == "job"
    assert var["type"] == "query"
    assert "label_values(http_requests_total, job)" == var["query"]


def test_generated_dashboard_datasource_is_consistent_across_panels():
    title, uid, panel_specs, template_vars = example_spec()
    dashboard = build_dashboard(title, uid, panel_specs, template_vars=template_vars)
    refs = {panel["datasource"]["uid"] for panel in dashboard["panels"]}
    assert len(refs) == 1


def test_generated_dashboard_template_vars_used_in_queries_are_declared():
    title, uid, panel_specs, template_vars = example_spec()
    dashboard = build_dashboard(title, uid, panel_specs, template_vars=template_vars)
    # validate_dashboard already checks this; this test asserts it explicitly fails
    # to validate when we strip the declared variable but queries still use it.
    dashboard["templating"]["list"] = [
        v for v in dashboard["templating"]["list"] if v["name"] != "instance"
    ]
    with pytest.raises(ValidationError):
        validate_dashboard(dashboard)
