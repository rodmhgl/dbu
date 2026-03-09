# 🤖 Teams Operator - Kubernetes Namespace Automation Controller

A lightweight Kubernetes controller that automatically provisions and cleans up team namespaces by polling the Teams API. Built with Python and the Kubernetes client library, it implements a reconciliation loop to keep namespaces in sync with registered teams.

## 🎯 Overview

The Teams Operator provides:
- **Namespace Provisioning**: Automatically creates `team-*` namespaces when teams are registered
- **Namespace Cleanup**: Removes namespaces when teams are deleted from the API
- **Reconciliation Loop**: Configurable polling interval to detect changes
- **Labels & Annotations**: Full traceability metadata on managed namespaces
- **Security Hardened**: Non-root, read-only filesystem, seccomp, dropped capabilities
- **RBAC Configured**: Minimal ClusterRole permissions for namespace management

## 📋 Prerequisites

**Required Software**:
- **Kubernetes cluster** with kubectl access
- **Teams API** deployed and accessible (see [Teams API README](../teams-api/README.md))
- **Container runtime** (Docker recommended for local development)
- **Network connectivity** for container image pulls

**Recommended Setup**:
- Complete the [Teams API deployment](../teams-api/README.md) first — the operator depends on it
- Have the Teams API accessible via its Kubernetes Service

**Verify Prerequisites**:
```bash
# Check Kubernetes access
kubectl cluster-info

# Verify Teams API is running
kubectl get pods -n teams-api

# Verify you can create cluster-scoped resources
kubectl auth can-i create clusterroles
kubectl auth can-i create namespaces
```

## 🏗️ Architecture

The Teams Operator sits between the Teams API and the Kubernetes API, acting as a bridge that translates team registrations into namespace resources:

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│                 │  GET     │                 │  CREATE  │                 │
│   Teams API     │◀────────│ Teams Operator  │────────▶│  Kubernetes API │
│  (FastAPI)      │ /teams  │  (Python)       │  DELETE  │                 │
│                 │         │                 │         │                 │
└─────────────────┘         └─────────────────┘         └─────────────────┘
                                    │                           │
                                    │  Reconciliation           │
                                    │  Loop (30s)               ▼
                                    │                   ┌─────────────────┐
                                    │                   │  team-backend   │
                                    │                   │  team-frontend  │
                                    │                   │  team-devops    │
                                    └──────────────────▶│  team-*         │
                                                        │  (Namespaces)   │
                                                        └─────────────────┘
```

**Reconciliation Flow**:
1. Operator polls `GET /teams` from the Teams API at a configurable interval (default: 30 seconds)
2. Compares the current team list against its known set of teams
3. For **new teams**: creates a `team-<sanitized-name>` namespace with labels and annotations
4. For **deleted teams**: removes the corresponding namespace
5. Logs a summary when changes are detected

## 🚀 Quick Start Deployment

### Option 1: Using Pre-built Container Images

The easiest way to get started uses the pre-built container image:

```bash
# Deploy the operator (includes ServiceAccount, ClusterRole, ClusterRoleBinding, and Deployment)
kubectl apply -f operator-deployment.yaml
```

**Container Images Available**:
- **Docker Hub**: `olivercodes01/teams-operator:0.0.1`

### Option 2: Build Locally

For development and customization:

```bash
# Build your own container image
docker build -t teams-operator:local .

# Update the deployment to use your local image
# Then deploy
kubectl apply -f operator-deployment.yaml
```

### Verify Deployment

```bash
# Check that the operator pod is running
kubectl get pods -n engineering-platform -l app=teams-operator

# Expected output:
# NAME                              READY   STATUS    RESTARTS   AGE
# teams-operator-xxxxxxxx-xxxxx     1/1     Running   0          2m

# Check operator logs to confirm it's connected
kubectl logs -n engineering-platform deployment/teams-operator

# Expected output:
# 2025-01-15 10:30:00,000 - teams-operator - INFO - 🚀 Teams Operator starting...
# 2025-01-15 10:30:00,001 - teams-operator - INFO - 📡 Teams API URL: http://teams-api-service.engineering-platform.svc.cluster.local:4200
# 2025-01-15 10:30:00,002 - teams-operator - INFO - ⏰ Poll interval: 30 seconds
# 2025-01-15 10:30:00,003 - teams-operator - INFO - Loaded in-cluster Kubernetes config
```

## 🔄 How It Works

### Reconciliation Loop

The operator uses a **poll-based reconciliation** model (not a CRD watch). Every `POLL_INTERVAL` seconds it:

1. Fetches all teams from the Teams API (`GET /teams`)
2. Compares team IDs against its in-memory set of known teams
3. Creates namespaces for any new teams
4. Deletes namespaces for any removed teams
5. Updates its known teams set

### Namespace Naming Convention

Team names are sanitized into valid Kubernetes namespace names using these rules:

| Input Team Name | Resulting Namespace |
|-----------------|---------------------|
| `Backend Team` | `team-backend-team` |
| `DevOps` | `team-devops` |
| `QA & Testing` | `team-qa-testing` |
| `My--Cool--Team` | `team-my-cool-team` |
| `  Spaces  ` | `team-spaces` |

**Rules applied**:
- Lowercased
- Non-alphanumeric characters replaced with hyphens
- Consecutive hyphens collapsed
- Leading/trailing hyphens stripped
- Truncated to 63 characters (Kubernetes limit)
- Prefixed with `team-`

### Labels and Annotations

Every managed namespace receives metadata for traceability:

**Labels**:
| Key | Example Value | Purpose |
|-----|---------------|---------|
| `app.kubernetes.io/managed-by` | `teams-operator` | Identifies managing controller |
| `teams.example.com/team-id` | `fc9402c5-2b26-...` | Links to Teams API record |
| `teams.example.com/team-name` | `backend-team` | Sanitized team name |

**Annotations**:
| Key | Example Value | Purpose |
|-----|---------------|---------|
| `teams.example.com/original-team-name` | `Backend Team` | Original unsanitized name |
| `teams.example.com/created-by` | `teams-operator` | Audit trail |
| `teams.example.com/team-id` | `fc9402c5-2b26-...` | Links to Teams API record |

### Observing in Action

Walk through a full lifecycle to see the operator working:

```bash
# 1. Watch namespaces in a separate terminal
kubectl get namespaces --watch

# 2. Create a team via the API
curl -X POST "http://<workspace-name>.coder:3002/teams" \
     -H "Content-Type: application/json" \
     -d '{"name": "Platform Team"}'

# 3. Wait ~30 seconds (one poll interval), then verify
kubectl get namespace team-platform-team --show-labels

# Expected output:
# NAME                  STATUS   AGE   LABELS
# team-platform-team    Active   10s   app.kubernetes.io/managed-by=teams-operator,...

# 4. Check the operator logs
kubectl logs -n engineering-platform deployment/teams-operator --tail=5

# Expected output:
# ... - teams-operator - INFO - ✅ Created namespace 'team-platform-team' for team 'Platform Team' (ID: ...)
# ... - teams-operator - INFO - 📊 Reconciliation complete: 1 teams, 1 namespaces

# 5. Delete the team via the API
team_id=$(curl -s "http://<workspace-name>.coder:3002/teams" | jq -r '.[0].id')
curl -X DELETE "http://<workspace-name>.coder:3002/teams/$team_id"

# 6. Wait ~30 seconds and verify namespace is removed
kubectl get namespaces | grep team-

# Expected output: (no team-* namespaces)
```

## 🔧 Configuration Options

### Environment Variables

| Variable | Default | Deployment Value | Description |
|----------|---------|------------------|-------------|
| `TEAMS_API_URL` | `http://teams-api-service:80` | `http://teams-api-service.engineering-platform.svc.cluster.local:4200` | Teams API base URL |
| `POLL_INTERVAL` | `30` | `30` | Reconciliation interval in seconds |

> **Note**: The deployment YAML overrides the code default for `TEAMS_API_URL` with the fully-qualified service DNS name because the operator runs in the `engineering-platform` namespace, not the same namespace as the Teams API.

### Resource Limits

The deployment configures conservative resource limits appropriate for a lightweight polling controller:

```yaml
resources:
  requests:
    memory: "128Mi"
    cpu: "100m"
  limits:
    memory: "256Mi"
    cpu: "200m"
```

### Security Context

The operator runs with a hardened security posture:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1001
  runAsGroup: 1001
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop:
    - ALL
  seccompProfile:
    type: RuntimeDefault
```

## 🔒 RBAC Configuration

The operator requires cluster-level permissions because **namespaces are cluster-scoped resources** — a namespaced `Role` cannot manage them.

### Resources Created

The deployment manifest provisions three RBAC resources:

| Resource | Name | Namespace | Purpose |
|----------|------|-----------|---------|
| `ServiceAccount` | `teams-operator` | `engineering-platform` | Pod identity |
| `ClusterRole` | `teams-operator` | *(cluster-scoped)* | Permission definitions |
| `ClusterRoleBinding` | `teams-operator` | *(cluster-scoped)* | Binds role to service account |

### Permissions Granted

| API Group | Resource | Verbs | Reason |
|-----------|----------|-------|--------|
| `""` (core) | `namespaces` | `get`, `list`, `create`, `update`, `patch`, `delete` | Full namespace lifecycle management |
| `""` (core) | `events` | `create` | Emit Kubernetes events for observability |

### Why ClusterRole vs Role?

Kubernetes namespaces are **cluster-scoped** resources. A `Role` is namespaced and can only grant access to resources within its own namespace. Since the operator needs to create and delete namespaces across the cluster, it must use a `ClusterRole` bound via a `ClusterRoleBinding`.

## 🚨 Troubleshooting

### Common Issues and Solutions

#### 1. Pod Not Starting

**Symptoms**: Pod stuck in `Pending`, `ImagePullBackOff`, or `CrashLoopBackOff`

**Diagnosis**:
```bash
# Check pod status and events
kubectl describe pod -n engineering-platform -l app=teams-operator

# Check logs
kubectl logs -n engineering-platform deployment/teams-operator

# Check node resources
kubectl top nodes
```

**Solutions**:
```bash
# If image pull issues, verify image exists
docker pull olivercodes01/teams-operator:0.0.1

# If resource issues, check cluster capacity
kubectl describe nodes

# If permission issues, check RBAC
kubectl auth can-i create namespaces --as=system:serviceaccount:engineering-platform:teams-operator
```

#### 2. API Connection Failure

**Symptoms**: Operator logs show `Error connecting to Teams API` repeatedly

**Diagnosis**:
```bash
# Check operator logs
kubectl logs -n engineering-platform deployment/teams-operator --tail=20

# Verify Teams API is running
kubectl get pods -n teams-api
kubectl get svc -n teams-api

# Test DNS resolution from operator namespace
kubectl run -n engineering-platform dns-test --rm -it --image=busybox -- nslookup teams-api-service.teams-api.svc.cluster.local
```

**Solutions**:
```bash
# Verify the TEAMS_API_URL matches the actual service
kubectl get svc -n teams-api -o wide

# If Teams API is not deployed yet, deploy it first
kubectl apply -f ../teams-api/deployment.yaml

# Restart operator after fixing API
kubectl rollout restart deployment/teams-operator -n engineering-platform
```

#### 3. Namespaces Not Being Created

**Symptoms**: Teams exist in API but no `team-*` namespaces appear

**Diagnosis**:
```bash
# Check operator logs for errors
kubectl logs -n engineering-platform deployment/teams-operator --tail=30

# Verify RBAC permissions
kubectl auth can-i create namespaces --as=system:serviceaccount:engineering-platform:teams-operator

# Check if namespaces already exist (409 conflict)
kubectl get namespaces | grep team-
```

**Solutions**:
```bash
# If RBAC is missing, reapply the deployment manifest
kubectl apply -f operator-deployment.yaml

# If operator state is stale, restart it
kubectl rollout restart deployment/teams-operator -n engineering-platform
```

#### 4. Namespaces Not Being Deleted

**Symptoms**: Teams are deleted from API but `team-*` namespaces remain

**Diagnosis**:
```bash
# Check operator logs for deletion errors
kubectl logs -n engineering-platform deployment/teams-operator | grep -i delete

# Check if namespace is stuck in Terminating state
kubectl get namespaces | grep Terminating

# Verify RBAC includes delete permission
kubectl auth can-i delete namespaces --as=system:serviceaccount:engineering-platform:teams-operator
```

**Solutions**:
```bash
# If namespace is stuck Terminating, check for finalizers
kubectl get namespace team-<name> -o json | jq '.spec.finalizers'

# If operator lost track (restart clears in-memory state), restart it
# It will re-sync on the next reconciliation cycle
kubectl rollout restart deployment/teams-operator -n engineering-platform
```

#### 5. Operator Restarting Frequently

**Symptoms**: Pod restart count increasing, `CrashLoopBackOff` status

**Diagnosis**:
```bash
# Check previous container logs
kubectl logs -n engineering-platform deployment/teams-operator --previous

# Check resource usage
kubectl top pods -n engineering-platform -l app=teams-operator

# Check liveness probe failures
kubectl describe pod -n engineering-platform -l app=teams-operator | grep -A5 "Liveness"
```

**Solutions**:
```bash
# If OOM killed, increase memory limits
kubectl patch deployment teams-operator -n engineering-platform \
  -p '{"spec":{"template":{"spec":{"containers":[{"name":"teams-operator","resources":{"limits":{"memory":"512Mi"}}}]}}}}'

# If Python exceptions, check logs for stack traces
kubectl logs -n engineering-platform deployment/teams-operator --tail=50
```

## 🧪 Testing

### Manual Testing Workflow

Complete test sequence to verify the operator end-to-end:

```bash
# 1. Ensure the Teams API is accessible
kubectl port-forward -n teams-api svc/teams-api-service 3002:4200 &

# 2. Verify API health
curl http://<workspace-name>.coder:3002/health

# 3. Check operator is running
kubectl get pods -n engineering-platform -l app=teams-operator

# 4. Create a team
curl -X POST "http://<workspace-name>.coder:3002/teams" \
     -H "Content-Type: application/json" \
     -d '{"name": "Test Operator Team"}'

# 5. Wait for reconciliation (up to 30 seconds)
sleep 35

# 6. Verify namespace was created
kubectl get namespace team-test-operator-team

# 7. Verify labels are correct
kubectl get namespace team-test-operator-team --show-labels

# 8. Delete the team
team_id=$(curl -s "http://<workspace-name>.coder:3002/teams" | jq -r '.[] | select(.name=="Test Operator Team") | .id')
curl -X DELETE "http://<workspace-name>.coder:3002/teams/$team_id"

# 9. Wait for reconciliation
sleep 35

# 10. Verify namespace was removed
kubectl get namespaces | grep team-test-operator-team
# Expected: no output (namespace deleted)
```

### Automated Verification Script

```bash
cat > test-operator.sh << 'EOF'
#!/bin/bash
set -e

BASE_URL="http://<workspace-name>.coder:3002"
POLL_WAIT=35
echo "Testing Teams Operator (waiting ${POLL_WAIT}s per reconciliation cycle)"

# Verify operator is running
echo "✅ Checking operator pod..."
kubectl get pods -n engineering-platform -l app=teams-operator | grep Running

# Create a test team
echo "✅ Creating test team..."
response=$(curl -s -X POST "$BASE_URL/teams" -H "Content-Type: application/json" -d '{"name": "OperatorTest"}')
team_id=$(echo $response | jq -r '.id')
echo "   Created team with ID: $team_id"

# Wait for reconciliation
echo "⏳ Waiting for reconciliation..."
sleep $POLL_WAIT

# Verify namespace exists
echo "✅ Verifying namespace created..."
kubectl get namespace team-operatortest

# Verify labels
echo "✅ Verifying namespace labels..."
kubectl get namespace team-operatortest -o jsonpath='{.metadata.labels.app\.kubernetes\.io/managed-by}' | grep -q "teams-operator"

# Delete the team
echo "✅ Deleting test team..."
curl -s -X DELETE "$BASE_URL/teams/$team_id" > /dev/null

# Wait for reconciliation
echo "⏳ Waiting for cleanup..."
sleep $POLL_WAIT

# Verify namespace removed
echo "✅ Verifying namespace removed..."
if kubectl get namespace team-operatortest 2>/dev/null; then
    echo "❌ Namespace still exists!"
    exit 1
fi

echo "🎉 All operator tests passed!"
EOF

chmod +x test-operator.sh
./test-operator.sh
```

## 🎯 Next Steps

### Integration with Other Components

1. **Teams API**: The operator depends on the [Teams API](../teams-api/README.md) — deploy it first
2. **Teams CLI**: Use the [CLI tool](../cli/README.md) to create/delete teams and watch the operator respond
3. **Teams UI**: Use the [web interface](../teams-app/README.md) for GUI-driven team management with automatic namespace provisioning

### Development Extensions

- **Resource Quotas**: Automatically apply ResourceQuotas to team namespaces
- **Network Policies**: Create default NetworkPolicies for team isolation
- **CRD-Based**: Migrate from polling to a Custom Resource Definition with a watch-based controller
- **Metrics**: Add Prometheus metrics for reconciliation counts, latency, and errors
- **LimitRanges**: Set default container resource constraints per team namespace

## 📝 Important Notes

### In-Memory State

The operator tracks known teams **in memory**. This means:
- **State is lost** when the pod restarts
- On restart, the operator re-syncs by fetching all teams and creating any missing namespaces
- Existing namespaces are handled gracefully (409 Conflict is treated as success)

### Single Replica

The deployment uses `replicas: 1` by design:
- Multiple replicas would create race conditions on namespace creation/deletion
- The operator is lightweight and does not require high availability
- If the pod restarts, reconciliation resumes automatically

### Namespace Naming Limits

- Kubernetes namespace names are limited to **63 characters**
- Very long team names will be **truncated** at the namespace level
- The `team-` prefix consumes 5 characters, leaving 58 for the sanitized name

### API Dependency

- The operator **requires the Teams API to be running** and accessible
- If the API is unreachable, the operator logs errors and retries on the next poll cycle
- No namespaces are created or deleted when the API is down

### Destructive Operations

- **Deleting a team from the API will delete the corresponding namespace** and all resources within it
- This is by design for the workshop, but would need safeguards in production (e.g., finalizers, confirmation, backup)

## ✅ Verification Checklist

Your Teams Operator setup is complete when:
- [ ] Operator pod running in `engineering-platform` namespace
- [ ] Operator logs show connection to Teams API
- [ ] Creating a team via API produces a `team-*` namespace within 30 seconds
- [ ] Managed namespaces have correct `app.kubernetes.io/managed-by: teams-operator` label
- [ ] Managed namespaces have `teams.example.com/team-id` annotation
- [ ] Deleting a team via API removes the corresponding namespace within 30 seconds
- [ ] Operator recovers gracefully if the Teams API is temporarily unavailable
- [ ] Operator restarts cleanly and re-syncs state after a pod restart

**Your namespace automation controller is ready to bridge team management with Kubernetes!** 🤖
