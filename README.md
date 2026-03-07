# README

## Flux Bootstrap

source .env

flux bootstrap github \
  --owner=$GITHUB_USER \
  --repository=dbu \
  --branch=main \
  --path=./clusters/staging \
  --personal

## AKS Credentials

```text
az account set --subscription 12345678-abcd-9ef0-ab12-c34567cd8e90
az aks get-credentials --resource-group rg-back-stack-aks-pe --name back-stack-aks-pe --overwrite-existing
kubelogin convert-kubeconfig -l azurecli
```

## TODO

### Foundation

- [X] install flux

### Compliance At the Point of Change (CAPOC)

- [X] Gatekeeper install
- [X] Gatekeeper policies
- [X] CAPOC policies

### Runtime Security

- [X] Falco install
- [X] Falco rules
- [ ] Trivy install
- [ ] Trivy integration with Gatekeeper?

### Monitoring

- [X] Kube Prometheus Stack Setup (w/ Ingress)

### Authentication

- [X] Keycloak

### Platform

- [X] Teams API install
- [X] Teams APP install
  - [X] Validate operation (Create/Delete)
- [X] Teams CLI install
- [X] Teams Operator install
  - [X] Validate operation (Create/Delete)
- [X] Flux Operator Install
