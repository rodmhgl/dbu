# PRD-004: Internal Developer Platform API / Control Plane

## Metadata

| Field | Value |
|-------|-------|
| **PRD ID** | PRD-004 |
| **Title** | Internal Developer Platform API / Control Plane |
| **Priority** | P1 — High |
| **Effort Estimate** | Medium (1–2 weeks) |
| **Dependencies** | All existing infrastructure components, PRD-003 (observability) |
| **Status** | Draft |

---

## 1. Problem Statement

The demo has many independently deployed subsystems — Gatekeeper, Falco, Flux, Keycloak, Longhorn, kube-prometheus-stack, and the Teams app stack — but there is no unified API that presents the platform as a coherent product. Understanding the state of the platform requires querying each system individually via `kubectl`, Grafana, or direct API calls.

A platform is more than a collection of tools. It needs a control plane that aggregates health, status, and capabilities into a single programmatic interface. Without this, the demo feels like infrastructure cobbled together rather than an intentional platform product.

## 2. Goals

- **G1**: A single `/platform/health` endpoint that reports the aggregated health of all platform subsystems.
- **G2**: A `/platform/status` endpoint that reports the GitOps sync state, policy enforcement status, and runtime security posture.
- **G3**: A `/platform/capabilities` endpoint that describes what the platform offers (self-service namespaces, monitoring, policy enforcement, etc.).
- **G4**: The demo tells the story: "This is a platform. Here is its health. Here is what it provides."

## 3. Non-Goals

- Platform management actions (restarting subsystems, changing configurations) through this API.
- Multi-cluster aggregation.
- Authentication/authorization on the platform API itself (demo scope).

## 4. Scope

### 4.1 Platform Health Endpoint

```
GET /platform/health
Response: {
  "status": "healthy" | "degraded" | "unhealthy",
  "timestamp": "2025-01-15T10:30:00Z",
  "subsystems": {
    "teams-api": {
      "status": "healthy",
      "details": { "teams_count": 4, "response_time_ms": 12 }
    },
    "keycloak": {
      "status": "healthy",
      "details": { "realm": "teams", "response_time_ms": 45 }
    },
    "gatekeeper": {
      "status": "healthy",
      "details": {
        "audit_pod": "running",
        "webhook_pods": 3,
        "constraint_templates": 4,
        "constraints": 3,
        "violations": 0
      }
    },
    "falco": {
      "status": "healthy",
      "details": { "pods_running": 3, "alerts_last_hour": 2 }
    },
    "flux": {
      "status": "healthy",
      "details": {
        "kustomizations_synced": 5,
        "kustomizations_total": 5,
        "last_sync": "2025-01-15T10:28:00Z"
      }
    },
    "monitoring": {
      "status": "healthy",
      "details": {
        "prometheus": "up",
        "grafana": "up",
        "alertmanager": "up"
      }
    },
    "longhorn": {
      "status": "healthy",
      "details": {
        "nodes": 3,
        "volumes": 5,
        "storage_available_gb": 120
      }
    }
  }
}
```

Aggregation logic: `healthy` if all subsystems report healthy; `degraded` if any single non-critical subsystem is unhealthy; `unhealthy` if any critical subsystem (Flux, Gatekeeper, Teams API) is unhealthy.

### 4.2 Platform Status Endpoint

```
GET /platform/status
Response: {
  "gitops": {
    "provider": "flux",
    "version": "2.7.x",
    "sync_status": "synced",
    "kustomizations": [
      { "name": "apps", "status": "Applied", "last_applied": "..." },
      { "name": "infrastructure", "status": "Applied", "last_applied": "..." },
      { "name": "monitoring", "status": "Applied", "last_applied": "..." }
    ]
  },
  "policy_enforcement": {
    "engine": "gatekeeper",
    "constraint_templates": [
      { "name": "k8srequiredlabels", "status": "enforced" },
      { "name": "codecoveragesimple", "status": "enforced" },
      { "name": "vulnerabilityscan", "status": "enforced" },
      { "name": "rootprevention", "status": "enforced" }
    ],
    "total_violations": 0,
    "audit_last_run": "2025-01-15T10:25:00Z"
  },
  "runtime_security": {
    "engine": "falco",
    "rules_loaded": 45,
    "alerts_last_24h": 3,
    "critical_alerts_last_24h": 0
  },
  "authentication": {
    "provider": "keycloak",
    "realm": "teams",
    "sso_enabled": true
  }
}
```

### 4.3 Platform Capabilities Endpoint

```
GET /platform/capabilities
Response: {
  "platform_name": "Engineering Platform",
  "version": "1.0.0",
  "capabilities": [
    {
      "name": "Team Self-Service",
      "description": "Create teams with auto-provisioned namespaces, quotas, and network policies",
      "endpoint": "/teams",
      "status": "available"
    },
    {
      "name": "GitOps Deployment",
      "description": "Automated deployments via Flux CD with drift detection",
      "status": "available"
    },
    {
      "name": "Policy Enforcement",
      "description": "Admission control via OPA Gatekeeper — root prevention, CVE scanning, code coverage",
      "status": "available"
    },
    {
      "name": "Runtime Security",
      "description": "Behavioral monitoring via Falco with custom rules for root detection",
      "status": "available"
    },
    {
      "name": "Observability",
      "description": "Prometheus metrics, Grafana dashboards, auto-provisioned per service",
      "status": "available"
    },
    {
      "name": "Authentication & Authorization",
      "description": "SSO via Keycloak with RBAC integration",
      "status": "available"
    },
    {
      "name": "Persistent Storage",
      "description": "Longhorn distributed storage with Azure Blob backup",
      "status": "available"
    }
  ]
}
```

### 4.4 UI — Platform Dashboard

A new "Platform Health" view in the Teams UI (or a standalone page):

- Traffic-light status indicators for each subsystem
- Flux sync status with timestamps
- Gatekeeper violation count (should be zero in a healthy platform)
- Falco alert summary
- Auto-refresh every 30 seconds

## 5. Technical Design

### 5.1 Architecture

The platform API is implemented as a new module within the existing Teams API FastAPI application:

```
teams-management/teams-api/
├── main.py
├── platform/
│   ├── __init__.py
│   ├── routes.py           # /platform/health, /platform/status, /platform/capabilities
│   ├── health_checker.py   # Async health checks for each subsystem
│   ├── flux_status.py      # Query Flux Kustomization CRs
│   ├── gatekeeper_status.py # Query constraint templates and violations
│   └── falco_status.py     # Query Falco metrics or API
```

### 5.2 Data Sources per Subsystem

| Subsystem | Data Source | Method |
|-----------|-----------|--------|
| Teams API | `localhost:8000/health` | Internal function call |
| Keycloak | `https://kc.kube-playground.io/realms/master` | HTTP GET |
| Gatekeeper | Kubernetes API: ConstraintTemplate, Constraint CRs | `kubernetes` Python client |
| Falco | Prometheus metrics via PromQL or Falco health endpoint | HTTP GET to Prometheus API |
| Flux | Kubernetes API: `Kustomization` CRs in `flux-system` | `kubernetes` Python client |
| Monitoring | `http://kube-prometheus-stack-prometheus:9090/-/healthy` | HTTP GET |
| Longhorn | Kubernetes API: Longhorn Node/Volume CRs | `kubernetes` Python client |

### 5.3 RBAC Requirements

The Teams API ServiceAccount needs additional read permissions:

```yaml
rules:
- apiGroups: ["kustomize.toolkit.fluxcd.io"]
  resources: ["kustomizations"]
  verbs: ["get", "list"]
- apiGroups: ["templates.gatekeeper.sh"]
  resources: ["constrainttemplates"]
  verbs: ["get", "list"]
- apiGroups: ["constraints.gatekeeper.sh"]
  resources: ["*"]
  verbs: ["get", "list"]
- apiGroups: ["longhorn.io"]
  resources: ["nodes", "volumes"]
  verbs: ["get", "list"]
```

### 5.4 Caching

Health checks are cached with a 30-second TTL to prevent excessive API calls. The cache is invalidated on each request if the TTL has expired. Stale data is returned with a `cached: true` flag if a subsystem check times out.

## 6. Demo Script

1. Hit the platform health endpoint: `curl http://<api>/platform/health | jq`.
2. Walk through each subsystem: "Gatekeeper is enforcing 4 policies with zero violations. Flux has all 5 kustomizations synced. Falco is running across all nodes."
3. Hit the capabilities endpoint: `curl http://<api>/platform/capabilities | jq`.
4. Narrate: "This is what our platform offers. It's not a collection of tools — it's a product with a defined feature set."
5. Open the Platform Dashboard in the UI. Show traffic-light indicators.
6. Optionally: deliberately break something (scale down Gatekeeper) and watch the health endpoint reflect `degraded` status. Then restore it.

## 7. Success Criteria

- [ ] `/platform/health` returns accurate status for all 7 subsystems.
- [ ] Aggregated status correctly computes `healthy`, `degraded`, or `unhealthy`.
- [ ] `/platform/status` returns Flux sync state, Gatekeeper policy state, and Falco alert counts.
- [ ] `/platform/capabilities` returns a complete list of platform features.
- [ ] Health check latency is under 5 seconds (with caching).
- [ ] UI dashboard renders platform health with auto-refresh.

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| CRD API access requires custom RBAC and CRD awareness | Medium | Medium | Use generic Kubernetes API calls with dynamic resource discovery |
| Health check to Keycloak times out through ingress | Medium | Low | Use internal service URL instead of ingress hostname |
| Flux CRD schema changes between versions | Low | Medium | Pin Flux version; use generic JSON deserialization |
| Too many Kubernetes API calls on each health check | Medium | Medium | Cache all results with 30s TTL; batch concurrent checks |

## 9. Future Considerations

- Platform SLOs: define and track platform-level service level objectives (e.g., "namespace provisioning < 60s P99").
- Incident status: integrate with an incident management system to show active incidents.
- Change log: surface recent platform changes (Flux commits, Gatekeeper policy updates).
- Platform CLI: `platform-cli status` as a developer-facing alternative to the API.
