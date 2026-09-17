# Grafana Dashboard Collection

A small, reusable collection of Grafana dashboard JSON models for a
typical Prometheus-scraped application: HTTP-layer metrics, host
infrastructure metrics (node_exporter style), and a couple of
custom business metrics. Includes a Python script that generates new
dashboard JSON from a simple declarative spec, and a test suite that
structurally validates every dashboard against the Grafana schema.

## Honest disclaimer: not visually verified in Grafana

**The Docker daemon was not available in the environment this project
was built in, so no live Grafana instance was started.** These
dashboards were never opened in a running Grafana UI and have not been
visually verified (no screenshots, no confirmation that panels render
pixel-for-pixel as intended).

Instead, every dashboard is validated **structurally**, in Python
(`lib/grafana_validate.py`, exercised by `tests/`):

- Required top-level Grafana schema fields are present (`title`, `uid`,
  `schemaVersion`, `version`, `panels`, `templating`, `time`).
- Every panel has the fields Grafana needs to render it (`id`, `type`,
  `title`, `gridPos`, `datasource`, `targets`), a supported panel
  `type`, and a `gridPos` that fits inside the 24-column grid.
- No two panels in the same dashboard overlap on the grid (checked via
  axis-aligned rectangle intersection over every panel pair).
- Every panel query (`targets[].expr`) is syntactically plausible
  PromQL: balanced parentheses/braces, and at least one token that
  looks like a metric name rather than only PromQL keywords.
- Every `$variable` referenced inside a panel query is actually
  declared in that dashboard's `templating.list`.
- Datasource references (`panel.datasource`) are consistent across all
  panels in a dashboard.

This gives strong confidence the JSON is well-formed and internally
consistent, but it is **not** a substitute for opening these dashboards
in a real Grafana instance and confirming the panels render, the
PromQL actually returns data against your Prometheus, and the
thresholds/units look right for your data. Treat that as the next step
before relying on these in production.

## Why this exists

A sibling project, `prometheus-monitoring-stack`, is a Flask app
instrumented with `prometheus_client` plus `prometheus.yml` /
`alerts.yml` for scraping and alerting. This repo is the other half of
that picture: the **dashboard (visualization) side**. It's built as its
own standalone, reusable collection — not copied from that repo — but
uses the same conventional Prometheus/`prometheus_client` /
`node_exporter` metric-naming conventions (`http_requests_total`,
`http_request_duration_seconds_bucket`, `node_cpu_seconds_total`,
etc.) so the dashboards would sensibly apply to that kind of
Prometheus-scraped app, or any app instrumented the same way.

## Dashboards

All dashboards live in `dashboards/*.json` and use a `$datasource`
template variable (type `datasource`, query `prometheus`) so every
panel points at the same Prometheus datasource consistently — pick
your Prometheus datasource once per dashboard and every panel follows.

### Application HTTP Overview (`application-http-overview.json`)

Metrics: `http_requests_total`, `http_request_duration_seconds_bucket`,
`http_requests_in_progress`. Template variable: `$job`.

- **HTTP Request Rate by Status** (time series) — `sum(rate(...)) by (status)`
- **Error Rate (5xx %)** (stat) — 5xx rate as a percentage of total rate
- **Request Latency Percentiles** (time series) — p50/p95/p99 via `histogram_quantile`
- **In-Progress Requests** (stat) — current in-flight request gauge
- **Top Endpoints by Request Rate** (table) — `topk(10, ...) by (path)`

### Infrastructure Overview (`infrastructure-overview.json`)

Metrics: `node_cpu_seconds_total`, `node_memory_MemAvailable_bytes`,
`node_memory_MemTotal_bytes`, `node_filesystem_avail_bytes`,
`node_filesystem_size_bytes`, `node_load1`. Template variable: `$instance`.

- **CPU Usage %** (time series)
- **Memory Usage %** (gauge)
- **Disk Usage % by Mount** (table)
- **System Load (1m average)** (time series)

### Business Metrics (`business-metrics.json`)

Metrics: `orders_processed_total` (counter), `active_users` (gauge).
Template variable: `$job`.

- **Orders Processed Rate** (time series)
- **Active Users** (stat)
- **Active Users (Gauge)** (gauge)
- **Orders Processed by Job** (table)

## Importing into a real Grafana instance

1. In Grafana, go to **Dashboards → New → Import**.
2. Upload one of the files in `dashboards/`, or paste its JSON.
3. When prompted, map the `datasource` variable to a Prometheus
   datasource already configured in your Grafana instance.
4. Confirm your Prometheus is actually scraping metrics with the names
   used here (or adjust the panel queries in the JSON to match your
   own metric names/labels).

Or via the HTTP API:

```bash
curl -X POST http://localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <API_KEY>" \
  -d "{\"dashboard\": $(cat dashboards/application-http-overview.json), \"overwrite\": true}"
```

## The generator script

`generator/generate_dashboard.py` builds a Grafana dashboard dict from
a plain Python spec instead of hand-copying JSON:

```python
from generator.generate_dashboard import build_dashboard, make_query_variable

job_var = make_query_variable("job", "Job", "cache_hits_total")

panel_specs = [
    {
        "title": "Cache Hit Rate",
        "type": "timeseries",
        "expr": 'sum(rate(cache_hits_total{job="$job"}[5m]))',
        "unit": "ops",
    },
    {
        "title": "Cache Size",
        "type": "stat",
        "expr": 'sum(cache_entries{job="$job"})',
    },
]

dashboard = build_dashboard("Cache Overview", "cache-overview", panel_specs, template_vars=[job_var])
```

It automatically:

- assigns panel `id`s,
- lays panels out on the 24-column grid two-per-row (`_autolayout`),
  guaranteeing no overlap by construction,
- attaches a consistent `${datasource}` reference to every panel,
- wires up `targets[].refId` for one or more PromQL expressions per panel,
- always includes the `$datasource` template variable, plus whatever
  `template_vars` you pass in (e.g. via `make_query_variable`).

Run it directly to print a small example dashboard to stdout:

```bash
python generator/generate_dashboard.py > dashboards/generated-example.json
```

The test suite (`tests/test_generator.py`) feeds the generator's own
example spec back through the same structural validator used for the
bundled dashboards, proving the generator's output is schema-valid —
not just that the bundled, hand-written examples are.

## Repository layout

```
dashboards/                       bundled Grafana dashboard JSON files
generator/generate_dashboard.py   spec -> dashboard JSON generator (stdlib only)
lib/grafana_validate.py           shared structural validation library
tests/test_dashboards.py          tests over the bundled dashboards
tests/test_generator.py           tests over the generator's output
.github/workflows/tests.yml       CI: runs pytest on Python 3.11 and 3.12
```

## Running the tests locally

```bash
pip install -r requirements.txt
pytest -v
```

## License

MIT — see [LICENSE](LICENSE).
