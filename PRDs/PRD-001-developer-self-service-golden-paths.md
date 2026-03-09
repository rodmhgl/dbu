# PRD-001: Developer Self-Service & Golden Paths

## Metadata

| Field | Value |
|-------|-------|
| **PRD ID** | PRD-001 |
| **Title** | Developer Self-Service & Golden Paths |
| **Priority** | P0 — Critical |
| **Effort Estimate** | Large (2–3 weeks) |
| **Dependencies** | Teams Operator (existing), Flux GitOps (existing) |
| **Status** | Draft |

---

## 1. Problem Statement

The Teams Operator currently creates bare namespaces when a team is registered. A developer who receives a new team namespace still needs to manually configure resource quotas, limit ranges, network policies, RBAC bindings, and service accounts before they can deploy anything. This contradicts the core platform engineering promise: developers should get a production-ready environment without filing tickets or hand-configuring infrastructure.

Additionally, there is no mechanism for developers to scaffold a new workload that follows organizational best practices. Every new service starts from scratch, leading to inconsistency across teams and repeated toil.

## 2. Goals

- **G1**: When a team namespace is provisioned, it arrives fully equipped with security, resource, and networking defaults — zero manual setup required.
- **G2**: Developers can scaffold a new workload (deployment + service + ingress + Kustomization) through a single API call or CLI command, receiving manifests that encode organizational standards.
- **G3**: The demo clearly illustrates the "paved road" concept: the platform makes the right thing the easy thing.

## 3. Non-Goals

- Full Backstage-style template marketplace (covered in PRD-002).
- Multi-cluster support for namespace provisioning.
- Custom resource definition (CRD) migration for the operator (potential future enhancement).

## 4. Scope

### 4.1 Namespace Enrichment

When the Teams Operator creates a `team-*` namespace, the following resources must also be created within that namespace:

#### ResourceQuota

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-default-quota
spec:
  hard:
    requests.cpu: "4"
    requests.memory: 8Gi
    limits.cpu: "8"
    limits.memory: 16Gi
    pods: "20"
    services: "10"
    persistentvolumeclaims: "5"
```

#### LimitRange

```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: team-default-limits
spec:
  limits:
  - default:
      cpu: 200m
      memory: 256Mi
    defaultRequest:
      cpu: 50m
      memory: 64Mi
    type: Container
```

#### Default NetworkPolicy

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
spec:
  podSelector: {}
  policyTypes:
  - Ingress
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-same-namespace
spec:
  podSelector: {}
  ingress:
  - from:
    - podSelector: {}
  policyTypes:
  - Ingress
```

#### ServiceAccount with Annotations

A default `team-deployer` ServiceAccount with labels linking back to the team record in the Teams API.

#### RBAC RoleBinding

A RoleBinding granting the team's Keycloak group `edit` access within their namespace (preparing for integration with Keycloak groups in the future).

### 4.2 Workload Scaffolding

A new API endpoint and CLI command that generates starter manifests for a new service:

#### API Endpoint

```
POST /teams/{team_id}/workloads
Body: { "name": "my-service", "type": "web" | "worker" | "cronjob", "port": 8080 }
Response: { "manifests": [...], "branch": "scaffold/my-service", "pr_url": "..." }
```

For the demo, the endpoint returns the generated manifests as a JSON payload. In a production scenario, it would push to a Git branch and open a PR.

#### CLI Command

```bash
teams-cli scaffold --team <team-id> --name my-service --type web --port 8080
```

Outputs Kustomization-structured files:

```
my-service/
├── kustomization.yaml
├── deployment.yaml
├── service.yaml
└── ingress.yaml
```

#### Template Standards Encoded

Every scaffolded workload includes:

- Security context (non-root, read-only root filesystem, drop ALL capabilities, seccomp RuntimeDefault)
- Resource requests and limits
- Liveness and readiness probes (with sensible defaults)
- `commit-sha` annotation placeholder (for Gatekeeper code coverage policy)
- Labels: `app.kubernetes.io/name`, `app.kubernetes.io/part-of`, `app.kubernetes.io/managed-by`
- Namespace set to the team's namespace

## 5. Technical Design

### 5.1 Operator Changes

The `teams_operator.py` reconciliation loop is extended. After `create_namespace()` succeeds, a new `provision_namespace_resources()` method creates the enrichment resources using the Kubernetes Python client.

Resource definitions are stored as Python dictionaries or loaded from a `templates/` directory in the operator container image. This keeps the templates versioned alongside the operator code.

### 5.2 Scaffolding Service

Two options (recommend Option A for the demo):

**Option A — Embedded in Teams API**: Add a `/teams/{team_id}/workloads` endpoint to the existing FastAPI app. Templates are Jinja2-rendered from a `templates/` directory. Returns generated YAML as the response body.

**Option B — Separate Service**: A new microservice (`scaffold-service`) that accepts requests and generates manifests. More realistic but heavier for a demo.

### 5.3 Idempotency

The operator must handle re-provisioning gracefully. If a namespace already exists and resources are already present, the operator should patch/update rather than fail. Use `server-side apply` semantics where possible, or check for existence before creation.

## 6. Demo Script

1. Show the operator running and the Teams API healthy.
2. Create a new team via the CLI: `teams-cli create "Payments Team"`.
3. Wait one reconciliation cycle (~30 seconds).
4. Show the namespace exists: `kubectl get ns team-payments-team`.
5. Show all enrichment resources: `kubectl get quota,limitrange,netpol,sa -n team-payments-team`.
6. Scaffold a workload: `teams-cli scaffold --team <id> --name checkout-api --type web --port 8080`.
7. Show the generated manifests and highlight the security context, probes, and labels.
8. Apply the manifests and show the deployment running in the team namespace.
9. Narrate: "The developer went from zero to a running, secured, policy-compliant service with two commands."

## 7. Success Criteria

- [ ] Namespace creation triggers automatic provisioning of ResourceQuota, LimitRange, NetworkPolicy, ServiceAccount, and RoleBinding.
- [ ] All enrichment resources carry `app.kubernetes.io/managed-by: teams-operator` labels.
- [ ] Scaffolding endpoint/CLI generates valid Kubernetes manifests that pass Gatekeeper validation.
- [ ] Scaffolded deployments include security context, resource limits, and health probes.
- [ ] Operator handles idempotent re-provisioning without errors.
- [ ] End-to-end demo completes in under 3 minutes.

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Operator reconciliation time makes demo feel slow | Medium | Medium | Reduce `POLL_INTERVAL` to 10s during demos; add a manual trigger endpoint |
| ResourceQuota values too restrictive for demo workloads | Low | Medium | Use generous defaults; document how to customize |
| Scaffolded manifests drift from Gatekeeper policies | Medium | High | Add a CI validation step that renders templates and runs `gator test` against them |

## 9. Future Considerations

- Migrate operator to CRD-based (watch model instead of polling) for faster reaction time.
- Support custom quota profiles (small/medium/large team sizes).
- GitOps integration: scaffolding pushes directly to a feature branch and creates a PR.
- Backstage template integration for a GUI-based scaffolding experience.
