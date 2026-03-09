# PRD-002: Developer Portal & Service Catalog

## Metadata

| Field | Value |
|-------|-------|
| **PRD ID** | PRD-002 |
| **Title** | Developer Portal & Service Catalog |
| **Priority** | P1 — High |
| **Effort Estimate** | Medium (1–2 weeks) |
| **Dependencies** | Teams API (existing), kube-prometheus-stack (existing), Keycloak (existing) |
| **Status** | Draft |

---

## 1. Problem Statement

The current demo has teams, deployments, monitoring, security policies, and auth — but there is no single place where a developer can see everything that matters to them. A developer has to context-switch between `kubectl`, Grafana, the Teams UI, and mental knowledge of what's deployed where.

Platform engineering emphasizes the platform as a product. A product needs a front door. Without a service catalog or portal view, the demo cannot show the discoverability, ownership, and self-service aspects that differentiate a platform from a pile of tools.

## 2. Goals

- **G1**: Provide a unified view of all deployed services, organized by team, accessible from the existing Teams UI.
- **G2**: Surface health status, ownership metadata, and links to observability tools (Grafana dashboards, API docs) for each service.
- **G3**: Demonstrate the concept of a lightweight internal developer portal without requiring Backstage or similar heavy infrastructure.

## 3. Non-Goals

- Full Backstage deployment or integration.
- TechDocs or documentation hosting within the portal.
- API gateway or traffic management features.
- CI/CD pipeline visibility (covered partially in PRD-008).

## 4. Scope

### 4.1 Platform API — Service Catalog Endpoints

New endpoints added to the Teams API (or a new lightweight service):

#### List Services by Team

```
GET /teams/{team_id}/services
Response: [
  {
    "name": "teams-api",
    "namespace": "engineering-platform",
    "kind": "Deployment",
    "replicas": { "desired": 1, "ready": 1 },
    "image": "ghcr.io/rodmhgl/teams-api:1.0.0",
    "health": "healthy",
    "endpoints": {
      "docs": "/docs",
      "health": "/health",
      "grafana": "https://monitoring.kube-playground.io/d/<dashboard-id>"
    },
    "labels": { ... },
    "created_at": "2025-01-15T10:30:00Z"
  }
]
```

#### Platform Overview

```
GET /platform/catalog
Response: {
  "teams": 4,
  "services": 8,
  "namespaces": 6,
  "services_by_team": {
    "Backend Team": ["teams-api", "checkout-service"],
    "Frontend Team": ["teams-ui"],
    ...
  }
}
```

### 4.2 Service Discovery Mechanism

Services are discovered through one or more of these methods (in priority order):

1. **Kubernetes API query**: List Deployments and StatefulSets across team namespaces, filtering by `app.kubernetes.io/managed-by` or presence in a `team-*` namespace.
2. **Annotation-based enrichment**: Services annotate themselves with metadata:
   - `platform.example.com/docs-url`: Link to API documentation
   - `platform.example.com/grafana-dashboard`: Grafana dashboard UID
   - `platform.example.com/description`: Human-readable description
   - `platform.example.com/owner-team`: Team ID reference
   - `platform.example.com/tier`: `critical` | `standard` | `experimental`
3. **Static registration** (fallback): A ConfigMap or JSON file listing known platform services and their metadata.

### 4.3 UI — Service Catalog Tab

A new tab or view in the existing Angular Teams UI:

#### Catalog List View

- Card-based grid of all known services
- Each card shows: service name, owning team, health status indicator (green/yellow/red), replica count, current image tag
- Filtering by team and health status
- Search by service name

#### Service Detail View

- Full metadata display (labels, annotations, image, creation date)
- Health status with last check timestamp
- Direct links: Grafana dashboard, API docs (Swagger), logs (if available)
- Resource usage summary (CPU/memory from metrics API if accessible)
- Team ownership with link back to team details

#### Platform Overview Dashboard

- Top-level counts: total teams, total services, healthy vs unhealthy
- Services grouped by team
- Recent events (new deployments, scaling events)

### 4.4 Health Aggregation

The catalog backend performs lightweight health checks:

- For services with an annotated health endpoint: HTTP GET and report status code
- For services without: use Kubernetes readiness status from the Deployment/Pod
- Health is cached with a configurable TTL (default: 60 seconds) to avoid excessive polling

## 5. Technical Design

### 5.1 Backend

Recommend extending the existing Teams API with new route modules:

```
teams-api/
├── main.py                  # Existing
├── catalog/
│   ├── __init__.py
│   ├── routes.py            # /platform/catalog, /teams/{id}/services
│   ├── discovery.py         # Kubernetes API queries
│   └── health_checker.py    # Async health check aggregator
```

The catalog module uses the Kubernetes Python client (already a dependency of the operator). The Teams API pod will need a ServiceAccount with read access to Deployments, Services, and Pods across team namespaces.

### 5.2 RBAC for Catalog

A new ClusterRole for the Teams API:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: teams-api-catalog-reader
rules:
- apiGroups: ["apps"]
  resources: ["deployments", "statefulsets"]
  verbs: ["get", "list"]
- apiGroups: [""]
  resources: ["services", "pods"]
  verbs: ["get", "list"]
- apiGroups: [""]
  resources: ["namespaces"]
  verbs: ["get", "list"]
```

### 5.3 Frontend

New Angular components added to the existing `teams-app`:

- `CatalogListComponent` — grid view with filtering
- `ServiceDetailComponent` — detail view with links
- `PlatformOverviewComponent` — summary dashboard
- `CatalogService` — API client for catalog endpoints

Navigation updated to include a "Service Catalog" tab alongside the existing "Teams" view.

### 5.4 Pre-Seeded Demo Data

For the demo, ensure the following services are deployed and annotated:

- `teams-api` in `engineering-platform` — annotated with docs URL and Grafana dashboard
- `teams-ui` in `engineering-platform` — annotated with Grafana dashboard
- `teams-operator` in `engineering-platform` — annotated as an internal service
- `keycloak` in `keycloak` — annotated as an infrastructure service
- At least one team-created workload in a `team-*` namespace (from PRD-001 scaffolding)

## 6. Demo Script

1. Open the Teams UI and navigate to the "Service Catalog" tab.
2. Show the platform overview: "We have 4 teams and 8 services running. All healthy."
3. Filter by a specific team. Show their services and health status.
4. Click into the `teams-api` service. Show metadata, health, and the direct link to Grafana.
5. Click the Grafana link — monitoring dashboard opens with live metrics.
6. Click the API docs link — Swagger UI opens.
7. Narrate: "Every developer can find any service, see who owns it, check if it's healthy, and jump straight to the tools they need. No Slack messages, no tickets."

## 7. Success Criteria

- [ ] `/platform/catalog` returns accurate counts of teams, services, and namespaces.
- [ ] `/teams/{team_id}/services` returns all deployments in the team's namespace with health status.
- [ ] Catalog UI renders service cards with health indicators, team ownership, and image tags.
- [ ] Clicking a service shows detail view with working links to Grafana and API docs.
- [ ] Health status reflects actual pod readiness (not stale data older than 60 seconds).
- [ ] UI is responsive and loads within 2 seconds.

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Kubernetes API queries are slow with many namespaces | Low (demo scale) | Medium | Cache results with 30s TTL; paginate API responses |
| Health check to external services times out | Medium | Low | Set 5s timeout per check; mark as "unknown" on timeout |
| RBAC not configured correctly, catalog returns empty | Medium | High | Include RBAC manifests in deployment; add startup validation |
| UI complexity increases Angular build time | Low | Low | Lazy-load catalog module |

## 9. Future Considerations

- Backstage integration: export catalog data as Backstage `catalog-info.yaml` entities.
- API scorecards: rate services on documentation completeness, security compliance, observability coverage.
- Dependency mapping: visualize service-to-service communication.
- Cost attribution per service (ties into PRD-007).
