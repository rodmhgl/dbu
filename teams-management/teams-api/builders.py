"""Workload manifest builders and models for the Teams API scaffolder.

Each builder function returns a plain dict representing a K8s manifest,
following the same pattern as the operator's resources.py.
"""

import re
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class WorkloadType(str, Enum):
    cronjob = "cronjob"
    web = "web"
    worker = "worker"


class WorkloadCreate(BaseModel):
    name: str
    port: Optional[int] = 8080
    type: WorkloadType


class WorkloadManifest(BaseModel):
    content: dict
    filename: str


class WorkloadScaffoldResponse(BaseModel):
    branch: str
    manifests: List[WorkloadManifest]
    namespace: str
    pr_url: Optional[str] = None
    team_id: str
    team_name: str
    workload_name: str
    workload_type: WorkloadType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sanitize_namespace_name(team_name: str) -> str:
    """Convert team name to valid Kubernetes namespace name.

    Duplicated from teams_operator.py so the API can compute namespace names
    without depending on the operator.
    """
    namespace = team_name.lower()
    namespace = "".join(c if c.isalnum() else "-" for c in namespace)
    namespace = "-".join(filter(None, namespace.split("-")))
    namespace = namespace.strip("-")

    prefix = "team-"
    max_base = 63 - len(prefix)
    if len(namespace) > max_base:
        namespace = namespace[:max_base].rstrip("-")

    return f"{prefix}{namespace}"


def sanitize_workload_name(name: str) -> str:
    """Sanitize a workload name to be a valid K8s resource name."""
    sanitized = name.lower()
    sanitized = re.sub(r"[^a-z0-9-]", "-", sanitized)
    sanitized = re.sub(r"-+", "-", sanitized)
    sanitized = sanitized.strip("-")
    if len(sanitized) > 63:
        sanitized = sanitized[:63].rstrip("-")
    return sanitized


# ---------------------------------------------------------------------------
# Security context helpers
# ---------------------------------------------------------------------------

def _pod_security_context() -> dict:
    return {
        "fsGroup": 1000,
        "runAsGroup": 1000,
        "runAsNonRoot": True,
        "runAsUser": 1000,
        "seccompProfile": {
            "type": "RuntimeDefault",
        },
    }


def _container_security_context() -> dict:
    return {
        "allowPrivilegeEscalation": False,
        "capabilities": {
            "drop": ["ALL"],
        },
        "readOnlyRootFilesystem": True,
    }


def _workload_labels(workload_name: str, team_name: str) -> dict:
    return {
        "app.kubernetes.io/managed-by": "teams-scaffolder",
        "app.kubernetes.io/name": workload_name,
        "app.kubernetes.io/part-of": sanitize_workload_name(team_name),
    }


def _resource_requirements() -> dict:
    return {
        "limits": {
            "cpu": "200m",
            "memory": "256Mi",
        },
        "requests": {
            "cpu": "50m",
            "memory": "64Mi",
        },
    }


# ---------------------------------------------------------------------------
# Manifest builders
# ---------------------------------------------------------------------------

def build_deployment(
    workload_name: str,
    team_name: str,
    workload_type: WorkloadType,
    port: int = 8080,
) -> dict:
    labels = _workload_labels(workload_name, team_name)

    container: dict = {
        "image": f"REPLACE_ME/{workload_name}:latest",
        "name": workload_name,
        "resources": _resource_requirements(),
        "securityContext": _container_security_context(),
    }

    if workload_type == WorkloadType.web:
        container["ports"] = [{"containerPort": port}]
        container["livenessProbe"] = {
            "httpGet": {"path": "/health", "port": port},
            "initialDelaySeconds": 30,
            "periodSeconds": 10,
        }
        container["readinessProbe"] = {
            "httpGet": {"path": "/health", "port": port},
            "initialDelaySeconds": 5,
            "periodSeconds": 5,
        }
    else:
        container["livenessProbe"] = {
            "exec": {"command": ["cat", "/tmp/healthy"]},
            "initialDelaySeconds": 30,
            "periodSeconds": 10,
        }
        container["readinessProbe"] = {
            "exec": {"command": ["cat", "/tmp/healthy"]},
            "initialDelaySeconds": 5,
            "periodSeconds": 5,
        }

    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "annotations": {
                "commit-sha": "REPLACE_ME",
            },
            "labels": labels,
            "name": workload_name,
        },
        "spec": {
            "replicas": 1,
            "selector": {
                "matchLabels": {
                    "app.kubernetes.io/name": workload_name,
                },
            },
            "template": {
                "metadata": {
                    "labels": labels,
                },
                "spec": {
                    "containers": [container],
                    "securityContext": _pod_security_context(),
                },
            },
        },
    }


def build_service(workload_name: str, team_name: str, port: int = 8080) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "labels": _workload_labels(workload_name, team_name),
            "name": workload_name,
        },
        "spec": {
            "ports": [
                {
                    "port": port,
                    "protocol": "TCP",
                    "targetPort": port,
                },
            ],
            "selector": {
                "app.kubernetes.io/name": workload_name,
            },
            "type": "ClusterIP",
        },
    }


def build_ingress(workload_name: str, team_name: str, port: int = 8080) -> dict:
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {
            "annotations": {
                "traefik.ingress.kubernetes.io/router.entrypoints": "websecure",
                "traefik.ingress.kubernetes.io/router.tls": "true",
            },
            "labels": _workload_labels(workload_name, team_name),
            "name": workload_name,
        },
        "spec": {
            "ingressClassName": "traefik",
            "rules": [
                {
                    "host": f"{workload_name}.kube-playground.io",
                    "http": {
                        "paths": [
                            {
                                "backend": {
                                    "service": {
                                        "name": workload_name,
                                        "port": {"number": port},
                                    },
                                },
                                "path": "/",
                                "pathType": "Prefix",
                            },
                        ],
                    },
                },
            ],
            "tls": [
                {
                    "hosts": [f"{workload_name}.kube-playground.io"],
                    "secretName": "star-kube-playground-io-tls",
                },
            ],
        },
    }


def build_cronjob(
    workload_name: str,
    team_name: str,
    schedule: str = "*/15 * * * *",
) -> dict:
    labels = _workload_labels(workload_name, team_name)

    return {
        "apiVersion": "batch/v1",
        "kind": "CronJob",
        "metadata": {
            "labels": labels,
            "name": workload_name,
        },
        "spec": {
            "jobTemplate": {
                "spec": {
                    "template": {
                        "metadata": {
                            "labels": labels,
                        },
                        "spec": {
                            "containers": [
                                {
                                    "image": f"REPLACE_ME/{workload_name}:latest",
                                    "name": workload_name,
                                    "resources": _resource_requirements(),
                                    "securityContext": _container_security_context(),
                                },
                            ],
                            "restartPolicy": "OnFailure",
                            "securityContext": _pod_security_context(),
                        },
                    },
                },
            },
            "schedule": schedule,
        },
    }


def build_kustomization(filenames: List[str]) -> dict:
    return {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "resources": sorted(filenames),
    }


def build_staging_overlay(workload_name: str, namespace: str) -> dict:
    return {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "namespace": namespace,
        "resources": [f"../../base/{workload_name}"],
    }


# ---------------------------------------------------------------------------
# Manifest orchestrator
# ---------------------------------------------------------------------------

def generate_workload_manifests(
    workload_name: str,
    team_name: str,
    workload_type: WorkloadType,
    port: int = 8080,
) -> List[WorkloadManifest]:
    manifests: List[WorkloadManifest] = []

    if workload_type == WorkloadType.web:
        manifests.append(
            WorkloadManifest(
                filename="deployment.yaml",
                content=build_deployment(workload_name, team_name, workload_type, port),
            )
        )
        manifests.append(
            WorkloadManifest(
                filename="service.yaml",
                content=build_service(workload_name, team_name, port),
            )
        )
        manifests.append(
            WorkloadManifest(
                filename="ingress.yaml",
                content=build_ingress(workload_name, team_name, port),
            )
        )
    elif workload_type == WorkloadType.worker:
        manifests.append(
            WorkloadManifest(
                filename="deployment.yaml",
                content=build_deployment(workload_name, team_name, workload_type, port),
            )
        )
    elif workload_type == WorkloadType.cronjob:
        manifests.append(
            WorkloadManifest(
                filename="cronjob.yaml",
                content=build_cronjob(workload_name, team_name),
            )
        )

    resource_filenames = [m.filename for m in manifests]
    manifests.append(
        WorkloadManifest(
            filename="kustomization.yaml",
            content=build_kustomization(resource_filenames),
        )
    )

    return manifests
