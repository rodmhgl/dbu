"""Unit tests for namespace enrichment resource builders."""

import unittest

from kubernetes import client

from resources import (
    MANAGED_BY_LABEL,
    _common_labels,
    build_limit_range,
    build_network_policy_allow_ingress_controller,
    build_network_policy_allow_prometheus,
    build_network_policy_allow_same_ns,
    build_network_policy_deny_ingress,
    build_resource_quota,
    build_role_binding,
    build_service_account,
    sanitize_label_value,
)

NS = "team-backend"
TEAM_ID = "abc-123"
TEAM_NAME = "Backend Team"


class TestSanitizeLabelValue(unittest.TestCase):
    def test_spaces_to_hyphens(self):
        self.assertEqual(sanitize_label_value("My Cool Team"), "my-cool-team")

    def test_special_chars_stripped(self):
        self.assertEqual(sanitize_label_value("R&D/Team.One"), "r-d-team-one")

    def test_consecutive_hyphens_collapsed(self):
        self.assertEqual(sanitize_label_value("a&&&&b"), "a-b")

    def test_leading_trailing_hyphens_stripped(self):
        self.assertEqual(sanitize_label_value("---hello---"), "hello")

    def test_truncated_to_63_chars(self):
        long_name = "a" * 100
        result = sanitize_label_value(long_name)
        self.assertLessEqual(len(result), 63)

    def test_truncation_strips_trailing_hyphen(self):
        name = "a" * 62 + "-b"
        result = sanitize_label_value(name)
        self.assertLessEqual(len(result), 63)
        self.assertTrue(result[-1].isalnum())

    def test_simple_name(self):
        self.assertEqual(sanitize_label_value("backend"), "backend")


class TestCommonLabels(unittest.TestCase):
    def test_labels_contain_required_keys(self):
        labels = _common_labels(TEAM_ID, TEAM_NAME)
        self.assertEqual(labels["app.kubernetes.io/managed-by"], MANAGED_BY_LABEL)
        self.assertEqual(labels["teams.example.com/team-id"], TEAM_ID)
        self.assertEqual(labels["teams.example.com/team-name"], "backend-team")

    def test_team_name_sanitized(self):
        labels = _common_labels(TEAM_ID, "My Cool Team")
        self.assertEqual(labels["teams.example.com/team-name"], "my-cool-team")

    def test_special_chars_in_team_name(self):
        labels = _common_labels(TEAM_ID, "R&D/Platform")
        self.assertEqual(labels["teams.example.com/team-name"], "r-d-platform")


class TestBuildResourceQuota(unittest.TestCase):
    def setUp(self):
        self.quota = build_resource_quota(NS, TEAM_ID, TEAM_NAME)

    def test_returns_v1_resource_quota(self):
        self.assertIsInstance(self.quota, client.V1ResourceQuota)

    def test_name_and_namespace(self):
        self.assertEqual(self.quota.metadata.name, "team-quota")
        self.assertEqual(self.quota.metadata.namespace, NS)

    def test_has_managed_by_label(self):
        self.assertEqual(
            self.quota.metadata.labels["app.kubernetes.io/managed-by"],
            MANAGED_BY_LABEL,
        )

    def test_hard_limits(self):
        hard = self.quota.spec.hard
        self.assertEqual(hard["requests.cpu"], "4")
        self.assertEqual(hard["requests.memory"], "8Gi")
        self.assertEqual(hard["limits.cpu"], "8")
        self.assertEqual(hard["limits.memory"], "16Gi")
        self.assertEqual(hard["pods"], "20")
        self.assertEqual(hard["services"], "10")
        self.assertEqual(hard["persistentvolumeclaims"], "5")


class TestBuildLimitRange(unittest.TestCase):
    def setUp(self):
        self.lr = build_limit_range(NS, TEAM_ID, TEAM_NAME)

    def test_returns_v1_limit_range(self):
        self.assertIsInstance(self.lr, client.V1LimitRange)

    def test_name_and_namespace(self):
        self.assertEqual(self.lr.metadata.name, "team-limits")
        self.assertEqual(self.lr.metadata.namespace, NS)

    def test_container_defaults(self):
        limit = self.lr.spec.limits[0]
        self.assertEqual(limit.type, "Container")
        self.assertEqual(limit.default, {"cpu": "200m", "memory": "256Mi"})
        self.assertEqual(limit.default_request, {"cpu": "50m", "memory": "64Mi"})


class TestBuildNetworkPolicyDenyIngress(unittest.TestCase):
    def setUp(self):
        self.np = build_network_policy_deny_ingress(NS, TEAM_ID, TEAM_NAME)

    def test_kind_and_name(self):
        self.assertEqual(self.np["kind"], "NetworkPolicy")
        self.assertEqual(self.np["metadata"]["name"], "deny-all-ingress")

    def test_namespace(self):
        self.assertEqual(self.np["metadata"]["namespace"], NS)

    def test_denies_all_ingress(self):
        self.assertEqual(self.np["spec"]["policyTypes"], ["Ingress"])
        self.assertEqual(self.np["spec"]["podSelector"], {})
        self.assertNotIn("ingress", self.np["spec"])

    def test_has_labels(self):
        self.assertEqual(
            self.np["metadata"]["labels"]["app.kubernetes.io/managed-by"],
            MANAGED_BY_LABEL,
        )


class TestBuildNetworkPolicyAllowSameNs(unittest.TestCase):
    def setUp(self):
        self.np = build_network_policy_allow_same_ns(NS, TEAM_ID, TEAM_NAME)

    def test_name(self):
        self.assertEqual(self.np["metadata"]["name"], "allow-same-namespace")

    def test_allows_intra_namespace(self):
        ingress_from = self.np["spec"]["ingress"][0]["from"]
        self.assertEqual(ingress_from, [{"podSelector": {}}])


class TestBuildNetworkPolicyAllowPrometheus(unittest.TestCase):
    def setUp(self):
        self.np = build_network_policy_allow_prometheus(NS, TEAM_ID, TEAM_NAME)

    def test_name(self):
        self.assertEqual(self.np["metadata"]["name"], "allow-prometheus-scrape")

    def test_allows_monitoring_namespace(self):
        ns_selector = self.np["spec"]["ingress"][0]["from"][0]["namespaceSelector"]
        self.assertEqual(
            ns_selector["matchLabels"]["kubernetes.io/metadata.name"], "monitoring"
        )

    def test_scrape_ports(self):
        ports = self.np["spec"]["ingress"][0]["ports"]
        port_numbers = [p["port"] for p in ports]
        self.assertEqual(port_numbers, [9090, 8080, 8000])


class TestBuildNetworkPolicyAllowIngressController(unittest.TestCase):
    def setUp(self):
        self.np = build_network_policy_allow_ingress_controller(NS, TEAM_ID, TEAM_NAME)

    def test_name(self):
        self.assertEqual(self.np["metadata"]["name"], "allow-ingress-controller")

    def test_allows_traefik_namespace(self):
        ns_selector = self.np["spec"]["ingress"][0]["from"][0]["namespaceSelector"]
        self.assertEqual(
            ns_selector["matchLabels"]["kubernetes.io/metadata.name"], "traefik"
        )


class TestBuildServiceAccount(unittest.TestCase):
    def setUp(self):
        self.sa = build_service_account(NS, TEAM_ID, TEAM_NAME)

    def test_returns_v1_service_account(self):
        self.assertIsInstance(self.sa, client.V1ServiceAccount)

    def test_name_and_namespace(self):
        self.assertEqual(self.sa.metadata.name, "team-deployer")
        self.assertEqual(self.sa.metadata.namespace, NS)

    def test_annotations(self):
        self.assertEqual(self.sa.metadata.annotations["teams.example.com/team-id"], TEAM_ID)

    def test_has_labels(self):
        self.assertEqual(
            self.sa.metadata.labels["app.kubernetes.io/managed-by"], MANAGED_BY_LABEL
        )


class TestBuildRoleBinding(unittest.TestCase):
    def setUp(self):
        self.rb = build_role_binding(NS, TEAM_ID, TEAM_NAME)

    def test_kind_and_name(self):
        self.assertEqual(self.rb["kind"], "RoleBinding")
        self.assertEqual(self.rb["metadata"]["name"], "team-edit-binding")

    def test_namespace(self):
        self.assertEqual(self.rb["metadata"]["namespace"], NS)

    def test_binds_to_edit_cluster_role(self):
        self.assertEqual(self.rb["roleRef"]["kind"], "ClusterRole")
        self.assertEqual(self.rb["roleRef"]["name"], "edit")

    def test_group_name_matches_namespace(self):
        subject = self.rb["subjects"][0]
        self.assertEqual(subject["kind"], "Group")
        self.assertEqual(subject["name"], NS)

    def test_has_labels(self):
        self.assertEqual(
            self.rb["metadata"]["labels"]["app.kubernetes.io/managed-by"],
            MANAGED_BY_LABEL,
        )


if __name__ == "__main__":
    unittest.main()
