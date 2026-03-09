# PRD-009: Multi-Tenancy & Namespace Isolation

## Metadata

| Field | Value |
|-------|-------|
| **PRD ID** | PRD-009 |
| **Title** | Multi-Tenancy & Namespace Isolation |
| **Priority** | P1 — High |
| **Effort Estimate** | Small (2–3 days) |
| **Dependencies** | Teams Operator (existing), PRD-001 (namespace enrichment) |
| **Status** | Draft |

---

## 1. Problem Statement

Team namespaces are created by the operator but have no network isolation. Any pod in any namespace can communicate with any other pod across the cluster. This is a significant security gap for a platform that claims to support multiple teams — a vulnerability or compromise in one team's workload could affect other teams.

Platform engineering requires strong tenant boundaries. Without network isolation, the demo cannot credibly claim multi-tenancy support. Combined with the Gatekeeper policies (which prevent root and enforce vulnerability scanning), network policies complete the defense-in-depth story.

## 2. Goals

- **G1**: Every team namespace is provisioned with default-deny NetworkPolicies that block all ingress from outside the namespace.
- **G2**: Explicit allow rules enable necessary cross-namespace communication (e.g., Prometheus scraping, ingress controller traffic).
- **G3**: The demo shows that inter-namespace traffic is blocked by default and must be explicitly allowed.
- **G4**: Infrastructure namespaces (monitoring, gatekeeper-system, flux-system, etc.) are exempt from team isolation rules.

## 3. Non-Goals

- Service mesh deployment (Istio, Linkerd) for mTLS or advanced traffic management.
- Egress policies (restricting outbound traffic from team namespaces).
- Network policy enforcement engine deployment (assumes the CNI plugin supports NetworkPolicy — Calico, Cilium, or similar).
- Per-service fine-grained policies within a team namespace.

## 4. Scope

### 4.1 Default NetworkPolicies for Team Namespaces

Applied automatically by the Teams Operator (PRD-001) when a team namespace is created:

#### Default Deny All Ingress

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: team-<name>
  labels:
    app.kubernetes.io/managed-by: teams-operator
    policy.platform.example.com/type: isolation
spec:
  podSelector: {}
  policyTypes:
  - Ingress
```

#### Allow Intra-Namespace Traffic

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-same-namespace
  namespace: team-<name>
  labels:
    app.kubernetes.io/managed-by: teams-operator
    policy.platform.example.com/type: isolation
spec:
  podSelector: {}
  ingress:
  - from:
    - podSelector: {}
  policyTypes:
  - Ingress
```

#### Allow Prometheus Scraping

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-prometheus-scrape
  namespace: team-<name>
  labels:
    app.kubernetes.io/managed-by: teams-operator
    policy.platform.example.com/type: monitoring
spec:
  podSelector: {}
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: monitoring
    ports:
    - protocol: TCP
      port: 9090
    - protocol: TCP
      port: 8080
    - protocol: TCP
      port: 8000
  policyTypes:
  - Ingress
```

#### Allow Ingress Controller Traffic

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-ingress-controller
  namespace: team-<name>
  labels:
    app.kubernetes.io/managed-by: teams-operator
    policy.platform.example.com/type: ingress
spec:
  podSelector: {}
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: traefik
  policyTypes:
  - Ingress
```

### 4.2 Platform Namespace Policies

For the `engineering-platform` namespace (where the Teams API, UI, and operator run), apply policies that allow:

- Intra-namespace traffic (API ↔ UI proxy)
- Ingress controller traffic (external access)
- Prometheus scraping
- Traffic from team namespaces to the Teams API (for the operator and any team-specific integrations)

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-team-namespaces-to-api
  namespace: engineering-platform
spec:
  podSelector:
    matchLabels:
      app: teams-api
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          app.kubernetes.io/managed-by: teams-operator
  policyTypes:
  - Ingress
```

### 4.3 Isolation Verification Demo

A demo script that proves isolation is working:

```bash
#!/bin/bash
# demos/network-isolation/test-isolation.sh

echo "--- Creating test pods in two team namespaces ---"

# Assume team-alpha and team-beta namespaces exist
kubectl run test-server --image=nginx --port=80 -n team-alpha
kubectl wait --for=condition=ready pod/test-server -n team-alpha

# Try to reach team-alpha's pod from team-beta
echo "--- Attempting cross-namespace traffic (should FAIL) ---"
kubectl run test-client --rm -it --image=busybox -n team-beta -- \
  wget --timeout=5 -qO- http://test-server.team-alpha.svc.cluster.local || \
  echo "❌ BLOCKED — cross-namespace traffic denied by NetworkPolicy"

# Try to reach team-alpha's pod from within team-alpha
echo "--- Attempting same-namespace traffic (should SUCCEED) ---"
kubectl run test-client --rm -it --image=busybox -n team-alpha -- \
  wget --timeout=5 -qO- http://test-server.team-alpha.svc.cluster.local && \
  echo "✅ ALLOWED — same-namespace traffic permitted"

# Cleanup
kubectl delete pod test-server -n team-alpha
```

### 4.4 Documentation

`demos/network-isolation/ISOLATION-MODEL.md`:

- Diagram showing traffic flow between namespaces
- Table of default policies and what they allow/deny
- How teams can request additional cross-namespace access (e.g., Team A's service needs to call Team B's API)
- How to add custom NetworkPolicies within a team namespace

## 5. Technical Design

### 5.1 Operator Changes

Extend the Teams Operator's `provision_namespace_resources()` method (from PRD-001) to create NetworkPolicy resources. The policies are defined as Python dictionaries in the operator code or loaded from templates.

### 5.2 CNI Requirements

NetworkPolicies require a CNI plugin that supports them. Common options:

- **Calico**: Full NetworkPolicy support (most common in production)
- **Cilium**: Full support with advanced features
- **Flannel**: Does NOT support NetworkPolicies
- **Azure CNI**: Supports NetworkPolicies with Azure Network Policy or Calico

For the demo on AKS, verify the CNI supports NetworkPolicy. If using Azure CNI, enable the network policy feature.

### 5.3 Policy Ordering

NetworkPolicies are additive. The `default-deny-ingress` policy blocks everything, and subsequent policies add specific allows. This is the standard "deny-all, allow-specific" model.

### 5.4 Namespace Labels

The policies rely on namespace labels for selectors:

- `kubernetes.io/metadata.name: monitoring` — built-in label for the monitoring namespace
- `kubernetes.io/metadata.name: traefik` — built-in label for the traefik namespace
- `app.kubernetes.io/managed-by: teams-operator` — custom label on team namespaces

These labels are already set by the operator or are built-in Kubernetes labels.

## 6. Demo Script

1. "Our platform enforces network isolation between teams by default. Let me show you."
2. Create two teams: `team-alpha` and `team-beta`.
3. Deploy a simple nginx pod in `team-alpha`.
4. Try to reach it from `team-beta`: "Blocked. Teams cannot access each other's workloads by default."
5. Try to reach it from within `team-alpha`: "Allowed. Traffic within a team is permitted."
6. Show the NetworkPolicies: `kubectl get netpol -n team-alpha`.
7. "But monitoring still works." Show Prometheus successfully scraping metrics from the team namespace.
8. Narrate: "Every team gets isolation by default. If Team A needs to talk to Team B, they request a policy change through the platform — it's explicit, auditable, and version-controlled in Git."

## 7. Success Criteria

- [ ] Every team namespace has default-deny-ingress, allow-same-namespace, allow-prometheus, and allow-ingress-controller NetworkPolicies.
- [ ] Cross-namespace traffic between team namespaces is blocked.
- [ ] Intra-namespace traffic is allowed.
- [ ] Prometheus can scrape metrics from team namespaces.
- [ ] Ingress controller can route traffic to team namespace services.
- [ ] Demo script proves isolation in under 2 minutes.

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| CNI does not support NetworkPolicy | Medium | High | Verify CNI before deployment; document requirements; test with `kubectl describe netpol` |
| Policies block legitimate platform traffic | Medium | High | Test all cross-namespace flows before demo; include allow rules for monitoring, ingress, and DNS |
| DNS resolution blocked by policies | Medium | High | Ensure kube-dns/CoreDNS traffic is allowed (egress policy or no egress restriction) |
| Demo test pods fail to start due to other policies (Gatekeeper) | Medium | Medium | Use Gatekeeper-compliant test pod manifests with security context |

## 9. Future Considerations

- Egress policies: restrict outbound traffic from team namespaces (e.g., only allow access to the Teams API and external registries).
- Service mesh: Istio/Linkerd for mTLS between services, providing encryption in transit.
- Custom policy requests: a self-service endpoint where teams can request cross-namespace communication, subject to platform team approval.
- Network policy visualization: a UI panel showing the network topology and policy enforcement points.
- Cilium integration for advanced observability (Hubble) and identity-based policies.
