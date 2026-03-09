# PRD-003: Observability Integration End-to-End

## Metadata

| Field | Value |
|-------|-------|
| **PRD ID** | PRD-003 |
| **Title** | Observability Integration End-to-End |
| **Priority** | P0 — Critical |
| **Effort Estimate** | Small–Medium (3–5 days) |
| **Dependencies** | Teams API (existing), kube-prometheus-stack (existing) |
| **Status** | Draft |

---

## 1. Problem Statement

The demo deploys kube-prometheus-stack with Grafana, and the Teams API runs as a FastAPI application — but there is no connection between them. The API exposes no application-level metrics, there is no ServiceMonitor for the Teams API, and there are no pre-built Grafana dashboards showing application behavior.

This means the monitoring stack and the application exist in parallel but never intersect. For a platform engineering demo, this is a significant gap: one of the primary value propositions of a platform is that observability is automatic. Developers deploy an app and metrics just appear.

## 2. Goals

- **G1**: The Teams API exposes Prometheus-format metrics at a `/metrics` endpoint covering request count, latency, error rates, and active team count.
- **G2**: A ServiceMonitor is deployed that automatically tells Prometheus to scrape the Teams API.
- **G3**: A pre-built Grafana dashboard is provisioned via ConfigMap that visualizes Teams API metrics out of the box.
- **G4**: The demo shows the full loop: deploy → metrics scraped → dashboard available — with zero manual configuration.

## 3. Non-Goals

- Distributed tracing (Jaeger/Tempo integration).
- Log aggregation (Loki/EFK stack).
- Alerting rules and PagerDuty/Slack notification channels.
- Custom metrics beyond standard HTTP and business metrics.

## 4. Scope

### 4.1 Teams API Instrumentation

Add Prometheus metrics to the FastAPI application using `prometheus-fastapi-instrumentator` or `prometheus-client`.

#### Metrics Exposed

| Metric Name | Type | Description |
|------------|------|-------------|
| `http_requests_total` | Counter | Total HTTP requests by method, path, status code |
| `http_request_duration_seconds` | Histogram | Request latency distribution by method and path |
| `http_requests_in_progress` | Gauge | Currently active requests |
| `teams_total` | Gauge | Current number of teams in the store |
| `teams_created_total` | Counter | Cumulative number of teams created |
| `teams_deleted_total` | Counter | Cumulative number of teams deleted |

#### Implementation

Add to `requirements.txt`:

```
prometheus-fastapi-instrumentator==6.1.0
```

Add to `main.py`:

```python
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Gauge, Counter

teams_gauge = Gauge('teams_total', 'Current number of teams')
teams_created_counter = Counter('teams_created_total', 'Total teams created')
teams_deleted_counter = Counter('teams_deleted_total', 'Total teams deleted')

Instrumentator().instrument(app).expose(app, endpoint="/metrics")
```

Update `create_team` and `delete_team` to increment the counters and update the gauge.

### 4.2 ServiceMonitor

Deploy a ServiceMonitor resource that targets the Teams API:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: teams-api
  namespace: engineering-platform
  labels:
    release: kube-prometheus-stack
spec:
  selector:
    matchLabels:
      app: teams-api
      component: backend
  endpoints:
  - port: http
    path: /metrics
    interval: 15s
    scrapeTimeout: 10s
  namespaceSelector:
    matchNames:
    - engineering-platform
```

The `release: kube-prometheus-stack` label is critical — the existing Prometheus instance uses `serviceMonitorSelector` filtered by this label.

### 4.3 Grafana Dashboard

A pre-built dashboard provisioned as a ConfigMap with the `grafana_dashboard: "1"` label so the Grafana sidecar auto-loads it.

#### Dashboard Panels

**Row 1 — Traffic Overview**:
- Request rate (requests/second) — timeseries
- Error rate (4xx + 5xx as percentage) — stat panel
- P50 / P95 / P99 latency — timeseries

**Row 2 — Business Metrics**:
- Current team count — single stat gauge
- Teams created over time — timeseries
- Teams deleted over time — timeseries

**Row 3 — Resource Health**:
- Active requests (in-progress gauge) — gauge panel
- Pod CPU usage — timeseries (from cAdvisor metrics)
- Pod memory usage — timeseries (from cAdvisor metrics)

#### Provisioning

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: teams-api-grafana-dashboard
  namespace: monitoring
  labels:
    grafana_dashboard: "1"
data:
  teams-api-dashboard.json: |
    { ... dashboard JSON ... }
```

The dashboard JSON will be generated using Grafana's export feature after manual creation, or authored directly using the Grafana dashboard JSON schema.

### 4.4 Teams Operator Metrics (Stretch)

If time permits, also instrument the Teams Operator:

| Metric Name | Type | Description |
|------------|------|-------------|
| `operator_reconciliations_total` | Counter | Total reconciliation cycles run |
| `operator_namespaces_created_total` | Counter | Total namespaces created |
| `operator_namespaces_deleted_total` | Counter | Total namespaces deleted |
| `operator_reconciliation_duration_seconds` | Histogram | Time spent per reconciliation cycle |
| `operator_api_errors_total` | Counter | Failed API calls to Teams API |

## 5. Technical Design

### 5.1 File Changes

```
teams-management/teams-api/
├── main.py                          # Add instrumentator + custom metrics
├── requirements.txt                 # Add prometheus-fastapi-instrumentator

apps/base/teams-api/
├── teams-api-servicemonitor.yaml    # New: ServiceMonitor
├── kustomization.yaml               # Updated: include ServiceMonitor

monitoring/controllers/base/kube-prometheus-stack/
├── teams-api-dashboard-cm.yaml      # New: Grafana dashboard ConfigMap
├── kustomization.yaml               # Updated: include dashboard CM
```

### 5.2 Container Image

The Teams API Dockerfile does not need changes beyond the updated `requirements.txt`. A new image version will be built and pushed via the existing GitHub Actions workflow.

### 5.3 Network Considerations

Prometheus (in `monitoring` namespace) needs to reach the Teams API (in `engineering-platform` namespace) on port 8000. Since there are no restrictive NetworkPolicies between these namespaces currently, this should work without changes. If PRD-009 (namespace isolation) is implemented first, an explicit NetworkPolicy allowing Prometheus scraping will be needed.

## 6. Demo Script

1. Show the Teams API running: `curl http://<api>/health`.
2. Hit the metrics endpoint: `curl http://<api>/metrics`. Show raw Prometheus metrics.
3. Open Grafana. Navigate to the "Teams API" dashboard — it's already there, auto-provisioned.
4. Show the dashboard with live data: request rate, latency, current team count.
5. Create several teams rapidly via the CLI or curl.
6. Watch the dashboard update in real-time: team count goes up, request rate spikes, latency stays low.
7. Delete a team. Watch the counters.
8. Narrate: "The developer deployed this API and got a full monitoring dashboard with zero configuration. The platform handles observability as a built-in capability."

## 7. Success Criteria

- [ ] `/metrics` endpoint returns valid Prometheus exposition format.
- [ ] ServiceMonitor is created and Prometheus target shows as "UP" in the Prometheus UI.
- [ ] Grafana dashboard is automatically loaded via sidecar (no manual import).
- [ ] Dashboard shows request rate, latency histograms, error rates, and team count.
- [ ] Creating/deleting teams is reflected in dashboard within 30 seconds.
- [ ] No manual Grafana configuration is needed — dashboard appears after deployment.

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| ServiceMonitor label selector doesn't match Prometheus config | Medium | High | Verify `serviceMonitorSelector` in Prometheus CR; match `release: kube-prometheus-stack` label |
| Grafana sidecar doesn't detect ConfigMap | Medium | Medium | Verify sidecar label filter matches `grafana_dashboard: "1"`; check sidecar logs |
| Metrics cardinality too high from path labels | Low | Medium | Use `prometheus-fastapi-instrumentator` grouping to collapse path parameters |
| `/metrics` endpoint exposes sensitive data | Low | Low | Prometheus metrics are numeric counters/gauges only; no PII exposure |

## 9. Future Considerations

- Alerting rules: PrometheusRule for error rate > 5%, latency P99 > 1s, team count drop to 0.
- SLO tracking: Pyrra or Sloth integration for request success rate SLOs.
- Distributed tracing: OpenTelemetry instrumentation with Tempo.
- Log correlation: structured JSON logging with trace IDs forwarded to Loki.
- Dashboard templates: auto-generate a dashboard for every scaffolded workload (ties into PRD-001).
