# PRD-006: Secrets Management Story

## Metadata

| Field | Value |
|-------|-------|
| **PRD ID** | PRD-006 |
| **Title** | Secrets Management Story |
| **Priority** | P2 — Medium |
| **Effort Estimate** | Medium (1–2 weeks) |
| **Dependencies** | SOPS/Age (existing), Flux (existing) |
| **Status** | Draft |

---

## 1. Problem Statement

The demo uses SOPS with Age encryption for secrets management, which is a solid GitOps-native approach. However, the secrets workflow is completely invisible to the demo audience. Encrypted secrets appear as opaque blobs in the repository, and there is no scripted flow showing how secrets are created, encrypted, committed, and decrypted by Flux at deployment time.

For a platform engineering demo, secrets management is a key operational concern that audiences expect to see addressed. Without making this workflow visible and demonstrable, the demo misses an opportunity to show how the platform handles sensitive data without compromising security or developer experience.

## 2. Goals

- **G1**: Make the existing SOPS/Age workflow visible and demonstrable with a scripted flow.
- **G2**: Add an External Secrets Operator (ESO) integration as a more production-realistic alternative that can be shown alongside SOPS.
- **G3**: Demonstrate secret rotation without cluster access — edit the encrypted file, push to Git, Flux applies the change.
- **G4**: Document both approaches (SOPS and ESO) with tradeoffs for the demo audience.

## 3. Non-Goals

- HashiCorp Vault deployment (too heavy for demo scope).
- Custom secrets management UI.
- Automated secret rotation schedules.
- Key management service (KMS) integration beyond Age.

## 4. Scope

### 4.1 SOPS/Age Demo Flow

A scripted, reproducible demonstration of the existing SOPS workflow:

#### Demo Script: `demos/secrets-management/sops-demo.sh`

```bash
#!/bin/bash
# Prerequisites: sops and age installed locally

# 1. Show the encrypted secret in the repo
echo "--- Encrypted secret in Git ---"
cat infrastructure/controllers/base/keycloak/keycloak-secrets.yaml | head -20

# 2. Show the Age public key (safe to display)
echo "--- Age public key (recipient) ---"
grep 'recipient:' infrastructure/controllers/base/keycloak/keycloak-secrets.yaml

# 3. Create a new secret using SOPS
echo "--- Creating a new encrypted secret ---"
cat > /tmp/demo-secret.yaml << 'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: demo-api-key
  namespace: engineering-platform
type: Opaque
stringData:
  api-key: "super-secret-api-key-12345"
EOF

sops --encrypt \
  --age age1wqmrjqvd55mqqesrq04ehf3rxnj7l6fvlz4en54mypkjq6urm39qv7lkep \
  --encrypted-regex '^(data|stringData)$' \
  /tmp/demo-secret.yaml > /tmp/demo-secret-encrypted.yaml

echo "--- Encrypted result ---"
cat /tmp/demo-secret-encrypted.yaml

# 4. Show that Flux decrypts automatically
echo "--- Flux decryption configuration ---"
grep -A4 'decryption:' clusters/staging/apps.yaml

# 5. Simulate rotation: re-encrypt with new value
echo "--- Rotating a secret value ---"
sops --set '["stringData"]["api-key"] "rotated-new-key-67890"' /tmp/demo-secret-encrypted.yaml
echo "Secret rotated. Commit and push to Git — Flux applies the change."
```

#### Supporting Documentation

`demos/secrets-management/SOPS-GUIDE.md` explaining:

- How SOPS encryption/decryption works
- The Age key pair model (public key in `.sops.yaml`, private key in cluster as `sops-age` secret)
- How Flux integrates with SOPS via the `decryption` spec
- How to rotate the Age key itself
- How to add new secrets

### 4.2 External Secrets Operator (ESO) Integration

Deploy ESO with a Kubernetes Secret backend (for demo simplicity) to show the pattern of external secret stores.

#### Components

1. **ESO Helm Release**: Deployed via Flux, similar to other infrastructure components.

```yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: external-secrets
spec:
  chart:
    spec:
      chart: external-secrets
      version: "0.10.x"
      sourceRef:
        kind: HelmRepository
        name: external-secrets
```

2. **SecretStore**: Configured to use the Kubernetes backend (no external vault needed):

```yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: kubernetes-backend
  namespace: engineering-platform
spec:
  provider:
    kubernetes:
      remoteNamespace: platform-secrets
      server:
        caProvider:
          type: ConfigMap
          name: kube-root-ca.crt
          key: ca.crt
      auth:
        serviceAccount:
          name: eso-reader
```

3. **ExternalSecret**: Demonstrates pulling a secret from the store:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: demo-external-secret
  namespace: engineering-platform
spec:
  refreshInterval: 1m
  secretStoreRef:
    name: kubernetes-backend
    kind: SecretStore
  target:
    name: demo-api-credentials
    creationPolicy: Owner
  data:
  - secretKey: username
    remoteRef:
      key: demo-source-secret
      property: username
  - secretKey: password
    remoteRef:
      key: demo-source-secret
      property: password
```

### 4.3 Comparison Documentation

`demos/secrets-management/COMPARISON.md`:

| Aspect | SOPS/Age | External Secrets Operator |
|--------|----------|--------------------------|
| Secret storage | In Git (encrypted) | External store (Vault, AWS SM, K8s) |
| GitOps native | Yes — secrets are in the repo | Partially — ExternalSecret CRs are in Git, values are not |
| Key management | Age key pair; private key in cluster | Depends on backend (IAM, tokens, certs) |
| Rotation | Re-encrypt and push to Git | Update in external store; ESO refreshes |
| Audit trail | Git history | External store audit log + K8s events |
| Complexity | Low | Medium |
| Production readiness | Good for small/medium scale | Better for large scale with central vault |

### 4.4 Team Namespace Secrets (Tie-in to PRD-001)

When the Teams Operator provisions a namespace (PRD-001), it can also create a default `SecretStore` reference in the team namespace, giving teams immediate access to the platform's secret management infrastructure.

## 5. Technical Design

### 5.1 Directory Structure

```
demos/secrets-management/
├── sops-demo.sh
├── SOPS-GUIDE.md
├── COMPARISON.md
└── eso-example/
    ├── secretstore.yaml
    ├── externalsecret.yaml
    └── source-secret.yaml

infrastructure/controllers/base/external-secrets/   # New (optional)
├── kustomization.yaml
├── namespace.yaml
├── release.yaml
└── repository.yaml
```

### 5.2 Flux Integration

The SOPS decryption is already configured in the Flux Kustomization specs. No changes needed for the SOPS portion.

For ESO, add to the infrastructure staging kustomization if included:

```yaml
# infrastructure/controllers/staging/kustomization.yaml
resources:
  - ./external-secrets  # New
```

## 6. Demo Script (Narrative)

**Option A — SOPS-focused (simpler)**:

1. "Secrets in our platform are encrypted in Git using SOPS and Age. Let me show you."
2. Show an encrypted secret file — point out the encrypted values and the SOPS metadata.
3. "The private key lives in the cluster. Flux decrypts secrets at apply time."
4. Create a new secret, encrypt it with SOPS, show the encrypted output.
5. "To rotate a secret, I update the encrypted file and push to Git. Flux handles the rest. No kubectl, no cluster access needed."

**Option B — SOPS + ESO comparison (richer)**:

1. Show the SOPS flow as above.
2. "For teams that need a central secret store, we also support External Secrets Operator."
3. Show the ExternalSecret CR. "The secret definition is in Git, but the actual value lives in an external store."
4. Update the source secret. Show ESO sync the change within 60 seconds.
5. Compare approaches: "SOPS is simpler and fully GitOps-native. ESO scales better for organizations with central vault infrastructure."

## 7. Success Criteria

- [ ] SOPS demo script runs end-to-end and produces a valid encrypted secret.
- [ ] Encrypted secret can be committed to Git and applied by Flux.
- [ ] ESO (if deployed) syncs an ExternalSecret within 60 seconds of source secret update.
- [ ] Comparison document clearly explains tradeoffs between approaches.
- [ ] SOPS guide covers key creation, encryption, decryption, rotation, and Flux integration.
- [ ] No plaintext secrets are ever committed to the repository.

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Demo machine doesn't have `sops` or `age` installed | Medium | High | Include installation commands in demo script preamble; provide pre-built demo environment |
| Age private key not available for demo decryption | Low | High | SOPS demo only shows encryption (public key); decryption is shown via Flux behavior |
| ESO adds complexity that distracts from the demo | Medium | Medium | Make ESO optional; lead with SOPS as the primary story |
| Audience expects Vault and is disappointed by simpler alternatives | Low | Low | Frame SOPS/ESO as production-proven; Vault as a backend ESO supports |

## 9. Future Considerations

- Vault integration as an ESO backend for enterprise demos.
- Secret scanning in CI (e.g., `gitleaks`) to catch accidental plaintext commits.
- Sealed Secrets as an additional alternative to document.
- Per-team encryption keys: each team has its own Age key pair for namespace-scoped secrets.
- Secret usage audit: track which pods consume which secrets via Kubernetes audit logs.
