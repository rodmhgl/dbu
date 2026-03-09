# PRD-007: Cost & Resource Visibility

## Metadata

| Field | Value |
|-------|-------|
| **PRD ID** | PRD-007 |
| **Title** | Cost & Resource Visibility |
| **Priority** | P2 — Medium |
| **Effort Estimate** | Small–Medium (3–5 days) |
| **Dependencies** | kube-prometheus-stack (existing), Teams Operator namespace labels (existing/PRD-001) |
| **Status** | Draft |

---

## 1. Problem Statement

The platform provisions namespaces per team and sets resource quotas, but there is no visibility into how much each team is actually consuming. Platform teams and engineering leadership commonly need to answer: "How much is each team's infrastructure costing us?" and "Who is over-provisioned or under-utilizing their resources?"

Without cost and resource visibility, the platform cannot demonstrate the FinOps angle of platform engineering — showing that centralized infrastructure management enables cost transparency and optimization.

## 2. Goals

- **G1**: Deploy OpenCost to provide per-namespace (per-team) cost attribution.
- **G2**: Surface resource utilization data (actual vs requested CPU/memory) per team namespace in a Grafana dashboard.
- **G3**: Demonstrate how namespace labels (from the Teams Operator) enable automatic cost grouping by team.
- **G4**: Provide a cost summary endpoint in the platform API.

## 3. Non-Goals

- Cloud billing API integration (AWS CUR, Azure Cost Management).
- Chargeback/showback automation.
- Cost alerting or budget enforcement.
- Multi-cluster cost aggregation.

## 4. Scope

### 4.1 OpenCost Deployment

Deploy OpenCost via Flux as a new infrastructure component:

```yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: opencost
spec:
  chart:
    spec:
      chart: opencost
      version: "1.42.x"
      sourceRef:
        kind: HelmRepository
        name: opencost
  values:
    opencost:
      prometheus:
        internal:
          serviceName: kube-prometheus-stack-prometheus
          namespaceName: monitoring
          port: 9090
      ui:
        enabled: true
        ingress:
          enabled: true
          hosts:
            - host: costs.kube-playground.io
```

### 4.2 Grafana Cost Dashboard

A pre-provisioned Grafana dashboard (ConfigMap with `grafana_dashboard: "1"` label) showing:

**Row 1 — Cluster Overview**:
- Total cluster cost (estimated monthly)
- Cost by namespace (bar chart)
- Cost trend over time (timeseries)

**Row 2 — Team Cost Breakdown**:
- Cost per team namespace (filtered by `app.kubernetes.io/managed-by: teams-operator` label)
- Table: namespace, CPU cost, memory cost, storage cost, total

**Row 3 — Resource Efficiency**:
- CPU utilization vs requests by namespace (utilization %)
- Memory utilization vs requests by namespace
- Over-provisioned namespaces (requests >> actual usage)

### 4.3 Platform API Cost Endpoint

```
GET /platform/costs
Response: {
  "period": "last_24h",
  "total_estimated_monthly": 245.60,
  "currency": "USD",
  "by_team": [
    {
      "team": "Backend Team",
      "namespace": "team-backend-team",
      "cpu_cost": 12.50,
      "memory_cost": 8.30,
      "storage_cost": 2.10,
      "total": 22.90
    },
    ...
  ],
  "infrastructure": {
    "monitoring": 45.00,
    "keycloak": 18.00,
    "gatekeeper": 12.00,
    "flux": 8.00,
    "platform_overhead": 83.00
  }
}
```

Data sourced from OpenCost's API (`/allocation`).

### 4.4 Resource Utilization Summary

```
GET /platform/resources
Response: {
  "cluster": {
    "cpu_capacity": "16 cores",
    "cpu_requested": "8.5 cores",
    "cpu_used": "3.2 cores",
    "memory_capacity": "64Gi",
    "memory_requested": "32Gi",
    "memory_used": "18Gi"
  },
  "by_namespace": [
    {
      "namespace": "team-backend-team",
      "cpu_requested": "400m",
      "cpu_used": "120m",
      "cpu_efficiency": "30%",
      "memory_requested": "512Mi",
      "memory_used": "210Mi",
      "memory_efficiency": "41%"
    },
    ...
  ]
}
```

## 5. Technical Design

### 5.1 Infrastructure Addition

```
infrastructure/controllers/base/opencost/
├── kustomization.yaml
├── namespace.yaml
├── release.yaml
├── repository.yaml
└── wildcard_crt.yaml        # If exposing via ingress

infrastructure/controllers/staging/opencost/
├── kustomization.yaml

monitoring/controllers/base/kube-prometheus-stack/
├── opencost-dashboard-cm.yaml   # New Grafana dashboard
```

### 5.2 OpenCost → Prometheus Integration

OpenCost reads cost data from Prometheus metrics (cAdvisor, node-exporter, kube-state-metrics — all already deployed via kube-prometheus-stack). No additional scraping configuration is needed.

### 5.3 Label-Based Cost Attribution

The Teams Operator (existing + PRD-001 enhancements) labels every team namespace with:

```yaml
labels:
  app.kubernetes.io/managed-by: teams-operator
  teams.example.com/team-id: <team-id>
  teams.example.com/team-name: <team-name>
```

OpenCost uses namespace labels for grouping. The Grafana dashboard filters by `managed-by: teams-operator` to show only team namespaces in the team cost breakdown.

### 5.4 Platform API Integration

The `/platform/costs` endpoint calls OpenCost's allocation API:

```
GET http://opencost.opencost.svc.cluster.local:9090/allocation/compute?window=24h&aggregate=namespace
```

Parses the response and enriches with team names from the Teams API.

## 6. Demo Script

1. Open Grafana, navigate to "Platform Costs" dashboard.
2. "Here's what our cluster costs look like. Total estimated monthly cost is $245."
3. Show the cost-by-namespace bar chart. "The monitoring stack is our biggest cost. Each team namespace runs about $15–25/month."
4. Show resource efficiency panel. "The Backend Team is only using 30% of their CPU requests. We could right-size their quotas to save money."
5. Hit the platform cost API: `curl http://<api>/platform/costs | jq`.
6. "This data is available programmatically. Finance can pull it, managers can see their team's spend, and the platform team can identify optimization opportunities."
7. Narrate: "The platform doesn't just provision infrastructure — it provides transparency into what that infrastructure costs."

## 7. Success Criteria

- [ ] OpenCost deployed and accessible via ingress or port-forward.
- [ ] OpenCost UI shows per-namespace cost breakdown.
- [ ] Grafana dashboard shows cost and resource efficiency panels with live data.
- [ ] Team namespaces are correctly grouped by team label in cost views.
- [ ] `/platform/costs` returns accurate cost data sourced from OpenCost.
- [ ] `/platform/resources` returns cluster and per-namespace utilization metrics.

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| OpenCost cost estimates are inaccurate without cloud pricing API | Medium | Low | Document that estimates use default pricing; sufficient for demo purposes |
| OpenCost resource requirements add to cluster cost | Low | Low | Use minimal resource requests; it's lightweight |
| Prometheus cardinality increase from OpenCost metrics | Low | Medium | Monitor Prometheus memory; OpenCost metrics are minimal |

## 9. Future Considerations

- Cloud billing integration (Azure Cost Management API) for accurate pricing.
- Budget alerts: notify team leads when their namespace exceeds a cost threshold.
- Right-sizing recommendations: suggest quota adjustments based on actual utilization.
- Cost allocation in the service catalog (PRD-002): show per-service cost alongside health status.
- FinOps dashboards for leadership with trend analysis and forecasting.
