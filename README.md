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
az account set --subscription 02892755-eecf-4df8-bc08-a55279be6b35
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
  - [ ] Falco rules
  - [ ] Trivy install
  - [ ] Trivy integration with Gatekeeper?

### Monitoring

  - [X] Kube Prometheus Stack Setup (w/ Ingress)

### Authentication

  - [X] Keycloak

### Platform

  - [-] Teams API install
  - [-] Teams APP install
  - [-] Teams CLI install
  - [-] Teams Operator install
  - [ ] Flux Operator Install