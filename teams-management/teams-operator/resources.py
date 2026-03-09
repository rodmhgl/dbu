"""
Namespace enrichment resource builders for the Teams Operator.

Each builder function returns a K8s resource (typed client object or dict)
ready to be applied to a team namespace.
"""

from kubernetes import client


MANAGED_BY_LABEL = "teams-operator"


def sanitize_label_value(value: str) -> str:
    """Sanitize a string to be a valid Kubernetes label value.

    Label values must be <= 63 chars and match [a-z0-9A-Z]([a-z0-9A-Z._-]*[a-z0-9A-Z])?.
    """
    sanitized = value.lower()
    sanitized = "".join(c if c.isalnum() else "-" for c in sanitized)
    sanitized = "-".join(filter(None, sanitized.split("-")))
    sanitized = sanitized.strip("-")
    if len(sanitized) > 63:
        sanitized = sanitized[:63].rstrip("-")
    return sanitized


def _common_labels(team_id: str, team_name: str) -> dict:
    """Return standard labels applied to all enrichment resources."""
    return {
        "app.kubernetes.io/managed-by": MANAGED_BY_LABEL,
        "teams.example.com/team-id": team_id,
        "teams.example.com/team-name": sanitize_label_value(team_name),
    }


def build_resource_quota(
    namespace_name: str, team_id: str, team_name: str
) -> client.V1ResourceQuota:
    return client.V1ResourceQuota(
        metadata=client.V1ObjectMeta(
            name="team-quota",
            namespace=namespace_name,
            labels=_common_labels(team_id, team_name),
        ),
        spec=client.V1ResourceQuotaSpec(
            hard={
                "requests.cpu": "4",
                "requests.memory": "8Gi",
                "limits.cpu": "8",
                "limits.memory": "16Gi",
                "pods": "20",
                "services": "10",
                "persistentvolumeclaims": "5",
            }
        ),
    )


def build_limit_range(
    namespace_name: str, team_id: str, team_name: str
) -> client.V1LimitRange:
    return client.V1LimitRange(
        metadata=client.V1ObjectMeta(
            name="team-limits",
            namespace=namespace_name,
            labels=_common_labels(team_id, team_name),
        ),
        spec=client.V1LimitRangeSpec(
            limits=[
                client.V1LimitRangeItem(
                    type="Container",
                    default={"cpu": "200m", "memory": "256Mi"},
                    default_request={"cpu": "50m", "memory": "64Mi"},
                )
            ]
        ),
    )


def build_network_policy_deny_ingress(
    namespace_name: str, team_id: str, team_name: str
) -> dict:
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {
            "name": "deny-all-ingress",
            "namespace": namespace_name,
            "labels": _common_labels(team_id, team_name),
        },
        "spec": {
            "podSelector": {},
            "policyTypes": ["Ingress"],
        },
    }


def build_network_policy_allow_same_ns(
    namespace_name: str, team_id: str, team_name: str
) -> dict:
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {
            "name": "allow-same-namespace",
            "namespace": namespace_name,
            "labels": _common_labels(team_id, team_name),
        },
        "spec": {
            "podSelector": {},
            "policyTypes": ["Ingress"],
            "ingress": [
                {
                    "from": [
                        {
                            "podSelector": {},
                        }
                    ]
                }
            ],
        },
    }


def build_network_policy_allow_prometheus(
    namespace_name: str, team_id: str, team_name: str
) -> dict:
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {
            "name": "allow-prometheus-scrape",
            "namespace": namespace_name,
            "labels": _common_labels(team_id, team_name),
        },
        "spec": {
            "podSelector": {},
            "policyTypes": ["Ingress"],
            "ingress": [
                {
                    "from": [
                        {
                            "namespaceSelector": {
                                "matchLabels": {
                                    "kubernetes.io/metadata.name": "monitoring",
                                }
                            }
                        }
                    ],
                    "ports": [
                        {"protocol": "TCP", "port": 9090},
                        {"protocol": "TCP", "port": 8080},
                        {"protocol": "TCP", "port": 8000},
                    ],
                }
            ],
        },
    }


def build_network_policy_allow_ingress_controller(
    namespace_name: str, team_id: str, team_name: str
) -> dict:
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {
            "name": "allow-ingress-controller",
            "namespace": namespace_name,
            "labels": _common_labels(team_id, team_name),
        },
        "spec": {
            "podSelector": {},
            "policyTypes": ["Ingress"],
            "ingress": [
                {
                    "from": [
                        {
                            "namespaceSelector": {
                                "matchLabels": {
                                    "kubernetes.io/metadata.name": "traefik",
                                }
                            }
                        }
                    ],
                }
            ],
        },
    }


def build_service_account(
    namespace_name: str, team_id: str, team_name: str
) -> client.V1ServiceAccount:
    return client.V1ServiceAccount(
        metadata=client.V1ObjectMeta(
            name="team-deployer",
            namespace=namespace_name,
            labels=_common_labels(team_id, team_name),
            annotations={
                "teams.example.com/team-id": team_id,
                "teams.example.com/team-name": sanitize_label_value(team_name),
            },
        ),
    )


def build_role_binding(
    namespace_name: str, team_id: str, team_name: str
) -> dict:
    return {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "RoleBinding",
        "metadata": {
            "name": "team-edit-binding",
            "namespace": namespace_name,
            "labels": _common_labels(team_id, team_name),
        },
        "roleRef": {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "ClusterRole",
            "name": "edit",
        },
        "subjects": [
            {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "Group",
                "name": namespace_name,
            }
        ],
    }
