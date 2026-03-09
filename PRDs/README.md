# Platform Engineering Demo — Enhancement PRD Index

## Overview

This document indexes all Product Requirements Documents (PRDs) for enhancing the platform engineering demo. The PRDs are organized by priority and include a dependency map for implementation sequencing.

## PRD Summary

| PRD | Title | Priority | Effort | Status |
|-----|-------|----------|--------|--------|
| [PRD-001](./PRD-001-developer-self-service-golden-paths.md) | Developer Self-Service & Golden Paths | P0 — Critical | Large (2–3 weeks) | Draft |
| [PRD-002](./PRD-002-developer-portal-service-catalog.md) | Developer Portal & Service Catalog | P1 — High | Medium (1–2 weeks) | Draft |
| [PRD-003](./PRD-003-observability-integration-e2e.md) | Observability Integration End-to-End | P0 — Critical | Small–Medium (3–5 days) | Draft |
| [PRD-004](./PRD-004-platform-api-control-plane.md) | Platform API / Control Plane | P1 — High | Medium (1–2 weeks) | Draft |
| [PRD-005](./PRD-005-policy-as-code-demo-flow.md) | Policy-as-Code Demo Flow | P0 — Critical | Small (2–3 days) | Draft |
| [PRD-006](./PRD-006-secrets-management.md) | Secrets Management Story | P2 — Medium | Medium (1–2 weeks) | Draft |
| [PRD-007](./PRD-007-cost-resource-visibility.md) | Cost & Resource Visibility | P2 — Medium | Small–Medium (3–5 days) | Draft |
| [PRD-008](./PRD-008-cicd-integration-tightening.md) | CI/CD Integration Tightening | P1 — High | Medium (1–2 weeks) | Draft |
| [PRD-009](./PRD-009-multi-tenancy-namespace-isolation.md) | Multi-Tenancy & Namespace Isolation | P1 — High | Small (2–3 days) | Draft |
| [PRD-010](./PRD-010-documentation-runbooks.md) | Documentation & Runbook Integration | P1 — High | Small–Medium (3–5 days) | Draft |

## Dependency Map

```
PRD-005 (Policy Demo)          ──── No dependencies, can start immediately
PRD-003 (Observability)        ──── No dependencies, can start immediately
PRD-009 (Namespace Isolation)  ──── No dependencies, can start immediately

PRD-001 (Self-Service)         ──── Benefits from PRD-009 (includes NetPol in provisioning)
PRD-008 (CI/CD Tightening)     ──── No hard dependencies

PRD-002 (Service Catalog)      ──── Benefits from PRD-003 (links to dashboards)
                                    Benefits from PRD-001 (richer namespace data)

PRD-004 (Platform API)         ──── Benefits from PRD-003 (monitoring health checks)
                                    Benefits from PRD-002 (catalog data)

PRD-006 (Secrets Management)   ──── No hard dependencies
PRD-007 (Cost Visibility)      ──── Benefits from PRD-001 (labeled namespaces for attribution)

PRD-010 (Documentation)        ──── Should be done LAST (documents everything above)
                                    Benefits from ALL other PRDs being complete
```

## Recommended Implementation Phases

### Phase 1 — Quick Wins & Core Demo Impact (Weeks 1–2)

These three PRDs deliver the most demo impact for the least effort:

1. **PRD-005**: Policy-as-Code Demo Flow — 2–3 days. Creates the "hero moment" where the audience sees policies in action. No code changes to existing services.
2. **PRD-003**: Observability Integration — 3–5 days. Connects the monitoring stack to the application. High visual impact in demos.
3. **PRD-009**: Namespace Isolation — 2–3 days. Adds NetworkPolicies to team namespaces. Completes the security story.

### Phase 2 — Platform Depth (Weeks 2–4)

4. **PRD-001**: Developer Self-Service & Golden Paths — 2–3 weeks. The largest effort but the most important platform engineering differentiator. Enriches namespace provisioning and adds workload scaffolding.
5. **PRD-008**: CI/CD Integration Tightening — 1–2 weeks. Closes the GitOps loop. Can be worked in parallel with PRD-001.

### Phase 3 — Platform Breadth (Weeks 4–6)

6. **PRD-004**: Platform API / Control Plane — 1–2 weeks. Aggregates health across all subsystems. Stronger after PRD-003 is complete.
7. **PRD-002**: Developer Portal & Service Catalog — 1–2 weeks. Adds the "front door" to the platform. Stronger after PRD-001 and PRD-003.

### Phase 4 — Polish & Extras (Weeks 6–8)

8. **PRD-007**: Cost & Resource Visibility — 3–5 days. Adds FinOps angle. Nice-to-have for the demo.
9. **PRD-006**: Secrets Management Story — 1–2 weeks. Makes existing SOPS workflow visible. Can be deprioritized if time is short.
10. **PRD-010**: Documentation & Runbook Integration — 3–5 days. Must be done last since it documents everything. Critical for enabling other presenters.

## Platform Engineering Principles Covered

Each PRD maps to core platform engineering principles:

| Principle | PRDs |
|-----------|------|
| **Self-Service** | PRD-001, PRD-002 |
| **Golden Paths** | PRD-001, PRD-008 |
| **Guardrails** | PRD-005, PRD-009 |
| **Observability** | PRD-003, PRD-004 |
| **GitOps** | PRD-008, PRD-006 |
| **Security** | PRD-005, PRD-006, PRD-009 |
| **Developer Experience** | PRD-001, PRD-002, PRD-010 |
| **Cost Transparency** | PRD-007 |
| **Platform as Product** | PRD-004, PRD-010 |

## Total Estimated Effort

| Phase | Effort | Calendar Time (1 developer) |
|-------|--------|-----------------------------|
| Phase 1 | ~2 weeks | Weeks 1–2 |
| Phase 2 | ~4 weeks | Weeks 2–5 |
| Phase 3 | ~3 weeks | Weeks 5–7 |
| Phase 4 | ~2 weeks | Weeks 7–8 |
| **Total** | **~11 weeks** | **~8 weeks with parallelism** |

With two contributors working in parallel, the full set of enhancements could be completed in approximately 5–6 weeks.
