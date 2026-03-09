# PRD-005: Policy-as-Code Demo Flow

## Metadata

| Field | Value |
|-------|-------|
| **PRD ID** | PRD-005 |
| **Title** | Policy-as-Code Demo Flow |
| **Priority** | P0 — Critical |
| **Effort Estimate** | Small (2–3 days) |
| **Dependencies** | Gatekeeper (existing), Gatekeeper constraint templates & policies (existing) |
| **Status** | Draft |

---

## 1. Problem Statement

The Gatekeeper policies are deployed and enforced, but there is no curated demo flow that shows them in action. A demo audience cannot see a policy reject a deployment, understand why it was rejected, or observe the corrected deployment succeed. The policies are invisible infrastructure rather than a demonstrable capability.

Effective platform demos need a "hero moment" — the point where the platform visibly prevents a mistake and guides the developer toward the correct path. Without intentionally non-compliant manifests and a scripted rejection/correction flow, the CAPOC (Compliance at the Point of Change) story has no impact.

## 2. Goals

- **G1**: Provide a set of intentionally non-compliant Kubernetes manifests that trigger each Gatekeeper policy.
- **G2**: Provide a companion set of compliant manifests that demonstrate the "corrected" version.
- **G3**: Include a runnable demo script that applies non-compliant manifests, captures rejection messages, then applies compliant manifests successfully.
- **G4**: Document the policy catalog: what each policy enforces, why it matters, and how to fix violations.

## 3. Non-Goals

- New Gatekeeper policies beyond what's already deployed.
- OPA unit testing framework (Conftest/gator) integration in CI (future consideration).
- Mutation webhooks that auto-fix violations.

## 4. Scope

### 4.1 Non-Compliant Manifests

A new `demos/policy-violations/` directory containing manifests that intentionally violate each policy:

#### 4.1.1 Root Prevention Violation

`01-root-container.yaml` — A deployment running as root (UID 0):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: insecure-app
  namespace: engineering-platform
  annotations:
    commit-sha: "demo123456"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: insecure-app
  template:
    metadata:
      labels:
        app: insecure-app
    spec:
      containers:
      - name: insecure-app
        image: nginx:latest
        # NO securityContext — defaults to root
```

**Expected rejection**: "Container insecure-app is configured to run as root (UID: -1). Gatekeeper policy violation."

#### 4.1.2 CVE Vulnerability Violation

`02-vulnerable-image.yaml` — A deployment using an image with known high CVEs exceeding the limit:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vulnerable-app
  namespace: engineering-platform
  annotations:
    commit-sha: "demo123456"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vulnerable-app
  template:
    metadata:
      labels:
        app: vulnerable-app
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1001
      containers:
      - name: vulnerable-app
        image: ubuntu:latest
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop: ["ALL"]
```

**Expected rejection**: "Image ubuntu:latest has 3 critical CVEs, exceeding maximum allowed (0)" (based on existing vulnerability data in the constraint).

#### 4.1.3 Code Coverage Violation

`03-low-coverage.yaml` — A deployment whose `commit-sha` maps to coverage below the minimum:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: untested-app
  namespace: engineering-platform
  annotations:
    commit-sha: "d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0a1b2c3"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: untested-app
  template:
    metadata:
      labels:
        app: untested-app
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1001
      containers:
      - name: untested-app
        image: ghcr.io/rodmhgl/teams-api:1.0.0
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop: ["ALL"]
```

**Expected rejection**: "Code coverage 67% is below required minimum of 80% for commit d4e5f6..." (the existing quality constraint has this SHA mapped to 67% coverage).

#### 4.1.4 Missing Commit SHA

`04-no-commit-sha.yaml` — A deployment without the required `commit-sha` annotation:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: untracked-app
  namespace: engineering-platform
  # No annotations at all
spec:
  replicas: 1
  selector:
    matchLabels:
      app: untracked-app
  template:
    metadata:
      labels:
        app: untracked-app
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1001
      containers:
      - name: untracked-app
        image: ghcr.io/rodmhgl/teams-api:1.0.0
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop: ["ALL"]
```

**Expected rejection**: "Missing required annotation: commit-sha"

#### 4.1.5 Unscanned Image

`05-unscanned-image.yaml` — A deployment using an image not present in the vulnerability data:

```yaml
# Uses a valid security context and commit-sha, but an unknown image
# Expected rejection: "No vulnerability scan data found for image ..."
```

### 4.2 Compliant Manifests

`demos/policy-compliant/` — Corrected versions of each non-compliant manifest:

- `01-secure-container.yaml` — Non-root, read-only filesystem, all capabilities dropped
- `02-scanned-image.yaml` — Uses an image present in CVE constraint data with acceptable counts
- `03-tested-code.yaml` — Uses a commit-sha that maps to 80%+ coverage
- `04-tracked-deployment.yaml` — Includes commit-sha annotation
- `05-known-image.yaml` — Uses an image present in the vulnerability scan data

### 4.3 Demo Script

`demos/run-policy-demo.sh`:

```bash
#!/bin/bash
set -e

echo "=========================================="
echo "  Policy-as-Code Demo — Gatekeeper in Action"
echo "=========================================="

echo ""
echo "--- Scenario 1: Root Container ---"
echo "Attempting to deploy a container running as root..."
kubectl apply -f policy-violations/01-root-container.yaml 2>&1 || true
echo ""
echo "✅ Blocked! Now deploying the secure version..."
kubectl apply -f policy-compliant/01-secure-container.yaml
echo ""

echo "--- Scenario 2: Vulnerable Image ---"
echo "Attempting to deploy an image with critical CVEs..."
kubectl apply -f policy-violations/02-vulnerable-image.yaml 2>&1 || true
echo ""
echo "✅ Blocked! Now deploying the scanned version..."
kubectl apply -f policy-compliant/02-scanned-image.yaml
echo ""

# ... repeat for each scenario ...

echo "--- Cleanup ---"
kubectl delete -f policy-compliant/ --ignore-not-found
echo ""
echo "🎉 Demo complete. All violations caught, all corrections accepted."
```

### 4.4 Policy Catalog Document

`demos/POLICY-CATALOG.md` — A reference document listing:

| Policy | Kind | Enforced In | What It Checks | Example Violation | How to Fix |
|--------|------|------------|----------------|-------------------|------------|
| Root Prevention | RootPrevention | default, production, staging, engineering-platform | Containers must not run as UID 0 or without explicit runAsUser | No `securityContext.runAsUser` set | Add `securityContext.runAsNonRoot: true` and `runAsUser: <non-zero>` |
| Vulnerability Scan | VulnerabilityScan | default, production, staging, engineering-platform | Images must have scan data; critical CVEs = 0; high CVEs ≤ 3 | Using `ubuntu:latest` (3 critical CVEs in constraint data) | Use scanned images; remediate CVEs before deployment |
| Code Coverage | CodeCoverageSimple | default, production, staging, engineering-platform | Deployments must have `commit-sha` annotation mapping to ≥ 80% coverage | Commit SHA maps to 67% coverage | Increase test coverage to ≥ 80% before deploying |

## 5. Technical Design

### 5.1 Directory Structure

```
demos/
├── policy-violations/
│   ├── 01-root-container.yaml
│   ├── 02-vulnerable-image.yaml
│   ├── 03-low-coverage.yaml
│   ├── 04-no-commit-sha.yaml
│   └── 05-unscanned-image.yaml
├── policy-compliant/
│   ├── 01-secure-container.yaml
│   ├── 02-scanned-image.yaml
│   ├── 03-tested-code.yaml
│   ├── 04-tracked-deployment.yaml
│   └── 05-known-image.yaml
├── run-policy-demo.sh
├── cleanup.sh
└── POLICY-CATALOG.md
```

### 5.2 Namespace Targeting

All demo manifests target `engineering-platform` namespace since the Gatekeeper constraints are scoped to `["default", "production", "staging", "engineering-platform"]`.

### 5.3 Idempotency

The demo script uses `|| true` after each non-compliant `kubectl apply` to prevent script termination on expected rejections. The cleanup script deletes all demo resources.

## 6. Demo Script (Narrative)

1. "Our platform enforces compliance at the point of change. Let me show you what happens when someone tries to deploy something that violates our policies."
2. Apply root container manifest. Show the Gatekeeper rejection message.
3. "The platform tells you exactly what's wrong and what to fix. Let's deploy the corrected version."
4. Apply secure container manifest. Show it succeeds.
5. Repeat for CVE and code coverage violations.
6. "Every deployment in our platform goes through these checks automatically. No manual reviews, no security tickets. The platform enforces the rules."
7. Clean up demo resources.

## 7. Success Criteria

- [ ] Each non-compliant manifest is rejected by Gatekeeper with a clear, descriptive error message.
- [ ] Each compliant manifest is accepted and the deployment succeeds.
- [ ] Demo script runs end-to-end in under 2 minutes.
- [ ] Policy catalog document accurately describes all active policies.
- [ ] Cleanup script removes all demo resources without errors.

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Gatekeeper webhook not ready, rejections don't fire | Low | High | Check webhook status before demo; include pre-flight check in script |
| Constraint data (CVE counts, coverage %) changed since manifests were written | Medium | Medium | Pin specific images and commit SHAs that are stable in constraint config |
| Demo manifests accidentally left deployed after demo | Medium | Low | Cleanup script + `kubectl delete` in demo script epilogue |
| Audience confused by Kubernetes-specific error messages | Medium | Medium | Pre-explain the policy catalog; narrate each rejection clearly |

## 9. Future Considerations

- `gator test` CI integration: run policy tests against all manifests in the repo as a GitHub Actions workflow.
- Dry-run mode: `--dry-run=server` to show rejections without attempting real creation.
- Policy dashboard in the UI showing active policies, recent violations, and compliance score (ties into PRD-004).
- Mutation webhooks that auto-inject security contexts or labels to fix common violations.
