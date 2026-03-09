# PRD-008: CI/CD Integration Tightening

## Metadata

| Field | Value |
|-------|-------|
| **PRD ID** | PRD-008 |
| **Title** | CI/CD Integration Tightening — Closing the GitOps Loop |
| **Priority** | P1 — High |
| **Effort Estimate** | Medium (1–2 weeks) |
| **Dependencies** | GitHub Actions workflows (existing), Flux (existing), GHCR (existing) |
| **Status** | Draft |

---

## 1. Problem Statement

The current CI/CD pipeline has a gap. The GitHub Actions workflows build container images and push them to GHCR with semantic versioning tags — but they do not update the Kubernetes deployment manifests in the GitOps repository. The image tag in `teams-api-deployment.yaml` is hardcoded to `ghcr.io/rodmhgl/teams-api:1.0.0` and must be manually updated after each build.

This breaks the GitOps loop. A true GitOps pipeline is: code push → image built → manifest updated → Flux deploys. The manual step in the middle undermines the automation story and introduces drift risk.

## 2. Goals

- **G1**: After a successful image build and push, the deployment manifest in the GitOps repo is automatically updated with the new image tag.
- **G2**: Flux detects the manifest change and deploys the new version automatically.
- **G3**: The entire flow from code push to running deployment is fully automated with no manual steps.
- **G4**: The demo can show the complete pipeline: commit → build → tag update → deploy → running.

## 3. Non-Goals

- Canary or blue-green deployment strategies.
- Rollback automation (Flux handles this via Git revert).
- Multi-environment promotion (staging → production).
- Build caching or build optimization.

## 4. Scope

### 4.1 Option A — GitHub Actions Manifest Update (Recommended for Demo)

Extend the existing GitHub Actions workflows to update the deployment manifest after a successful image push.

#### Workflow Addition (teams-api-build.yml)

Add a new job after `build-and-push`:

```yaml
update-manifest:
  name: Update Deployment Manifest
  runs-on: ubuntu-latest
  needs: build-and-push
  steps:
    - name: Checkout
      uses: actions/checkout@v4
      with:
        token: ${{ secrets.GITHUB_TOKEN }}

    - name: Update image tag in deployment
      run: |
        NEW_TAG="${{ needs.release.outputs.new_release_version }}"
        sed -i "s|image: ghcr.io/rodmhgl/teams-api:.*|image: ghcr.io/rodmhgl/teams-api:${NEW_TAG}|" \
          apps/base/teams-api/teams-api-deployment.yaml

    - name: Update commit-sha annotation
      run: |
        SHORT_SHA="${GITHUB_SHA::12}"
        sed -i "s|commit-sha:.*|commit-sha: ${SHORT_SHA}|" \
          apps/base/teams-api/teams-api-deployment.yaml

    - name: Commit and push
      run: |
        git config user.name "github-actions[bot]"
        git config user.email "github-actions[bot]@users.noreply.github.com"
        git add apps/base/teams-api/teams-api-deployment.yaml
        git commit -m "chore: update teams-api image to ${{ needs.release.outputs.new_release_version }} [skip ci]"
        git push
```

The `[skip ci]` tag in the commit message prevents an infinite loop of builds.

#### Same Pattern for Teams UI

Apply the identical pattern to the `teams-ui-build.yml` workflow, updating `teams-ui-deployment.yaml`.

### 4.2 Option B — Flux Image Automation (Production-Grade)

Deploy Flux's image-reflector-controller and image-automation-controller for a more robust, Kubernetes-native approach.

#### Components

1. **Image Repository**: Tells Flux to watch a container registry for new tags.

```yaml
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImageRepository
metadata:
  name: teams-api
  namespace: flux-system
spec:
  image: ghcr.io/rodmhgl/teams-api
  interval: 5m
  secretRef:
    name: ghcr-credentials
```

2. **Image Policy**: Defines which tags to track (semver, alphabetical, etc.).

```yaml
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImagePolicy
metadata:
  name: teams-api
  namespace: flux-system
spec:
  imageRepositoryRef:
    name: teams-api
  policy:
    semver:
      range: ">=1.0.0"
```

3. **Image Update Automation**: Tells Flux to update manifests and commit changes.

```yaml
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImageUpdateAutomation
metadata:
  name: teams-api
  namespace: flux-system
spec:
  interval: 5m
  sourceRef:
    kind: GitRepository
    name: flux-system
  git:
    checkout:
      ref:
        branch: main
    commit:
      author:
        email: flux@kube-playground.io
        name: Flux Image Automation
      messageTemplate: "chore: update images {{ range .Changed.Changes }}{{ .OldValue }} → {{ .NewValue }} {{ end }}"
    push:
      branch: main
  update:
    path: ./apps
    strategy: Setters
```

4. **Manifest Marker**: Add a comment marker to the deployment:

```yaml
image: ghcr.io/rodmhgl/teams-api:1.0.0 # {"$imagepolicy": "flux-system:teams-api"}
```

#### Additional Flux Components Required

Add to `flux-instance.yaml`:

```yaml
components:
  - source-controller
  - kustomize-controller
  - helm-controller
  - notification-controller
  - image-reflector-controller     # New
  - image-automation-controller    # New
```

### 4.3 Commit SHA Propagation

Both options should also update the `commit-sha` annotation in the deployment manifest. This is critical because the Gatekeeper code coverage policy uses this annotation to look up test coverage data.

The workflow (Option A) or image automation commit (Option B) should update:

```yaml
metadata:
  annotations:
    commit-sha: <new-12-char-sha>
```

And the code coverage constraint data should be updated to include the new SHA with its coverage percentage. For the demo, this can be mocked by adding the SHA to the quality constraint's `coverageData` map.

### 4.4 Notification Integration (Stretch)

Configure Flux notifications to report deployment status:

```yaml
apiVersion: notification.toolkit.fluxcd.io/v1beta3
kind: Alert
metadata:
  name: deployment-alerts
  namespace: flux-system
spec:
  providerRef:
    name: github-status
  eventSources:
  - kind: Kustomization
    name: apps
  eventSeverity: info
```

This would post GitHub commit statuses showing whether the deployment succeeded.

## 5. Technical Design

### 5.1 Recommendation

For the demo, **Option A (GitHub Actions manifest update)** is recommended because:

- It's simpler to understand for a demo audience.
- It doesn't require additional Flux components.
- The flow is visible in GitHub Actions logs.
- It's easier to debug.

Option B should be documented as the "production-grade" approach and can be demonstrated as a future enhancement.

### 5.2 Workflow Trigger Prevention

The manifest update commit must not trigger another CI build. Strategies:

- `[skip ci]` in the commit message (GitHub Actions respects this).
- Path filtering: the build workflow only triggers on `teams-management/teams-api/**` changes, not `apps/**` changes (already configured).

### 5.3 Race Conditions

If two builds complete simultaneously, the second `git push` may fail due to a non-fast-forward. Mitigation:

- Pull before push in the workflow step.
- Use `git pull --rebase` before committing.
- Or: use Flux Image Automation (Option B) which handles this natively.

## 6. Demo Script

1. "Let me show you the complete pipeline. I'll make a code change to the Teams API."
2. Show the current running image version: `kubectl get deployment teams-api -n engineering-platform -o jsonpath='{.spec.template.spec.containers[0].image}'`.
3. Make a code change (or trigger `workflow_dispatch` on the build workflow).
4. Show GitHub Actions: semantic release creates a new version, image is built and pushed.
5. Show the manifest update commit: "The pipeline automatically updated the deployment manifest with the new image tag."
6. Show Flux sync: `flux get kustomizations` — the `apps` kustomization picks up the change.
7. Show the new version running: `kubectl get deployment teams-api -n engineering-platform -o jsonpath='{.spec.template.spec.containers[0].image}'`.
8. Narrate: "From code push to running deployment, fully automated. No manual image tag updates, no kubectl apply. Git is the single source of truth."

## 7. Success Criteria

- [ ] GitHub Actions workflow updates the deployment manifest after successful image push.
- [ ] Commit message includes `[skip ci]` to prevent infinite loops.
- [ ] Flux detects the manifest change and deploys the new image within 10 minutes (one reconciliation cycle).
- [ ] `commit-sha` annotation is updated alongside the image tag.
- [ ] No manual intervention required between code push and deployment.
- [ ] Both teams-api and teams-ui pipelines are updated.

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Infinite CI loop from manifest update commit | High (if not handled) | High | `[skip ci]` in commit message + path filtering on workflow triggers |
| Race condition on concurrent pushes | Low (demo scale) | Medium | `git pull --rebase` before push; or use Flux Image Automation |
| GITHUB_TOKEN lacks push permissions | Medium | High | Ensure `contents: write` permission is set (already present in workflow) |
| Flux reconciliation delay makes demo feel slow | Medium | Medium | Run `flux reconcile kustomization apps` manually during demo for instant effect |

## 9. Future Considerations

- Multi-environment promotion: build → staging manifest → (manual approval) → production manifest.
- Flux Image Automation (Option B) for production deployments.
- GitHub commit status updates from Flux showing deployment success/failure.
- Automated rollback: if health checks fail after deployment, Flux reverts to the previous Git commit.
- Integration with the code coverage pipeline: the build workflow also runs tests, computes coverage, and updates the Gatekeeper constraint data.
