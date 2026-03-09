"""Unit tests for Teams Operator enrichment logic."""

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from kubernetes.client.rest import ApiException


def _make_api_exception(status: int) -> ApiException:
    """Build a minimal ApiException with the given HTTP status."""
    exc = ApiException(status=status)
    exc.status = status
    return exc


class TestApplyCoreResource(unittest.TestCase):
    """Tests for TeamsOperator._apply_core_resource()."""

    def _make_operator(self):
        with patch("teams_operator.config.load_incluster_config"), \
             patch("teams_operator.client.CoreV1Api"), \
             patch("teams_operator.client.NetworkingV1Api"), \
             patch("teams_operator.client.RbacAuthorizationV1Api"):
            from teams_operator import TeamsOperator
            return TeamsOperator()

    def test_create_succeeds(self):
        op = self._make_operator()
        create_fn = MagicMock()
        patch_fn = MagicMock()
        result = op._apply_core_resource("TestResource", "ns", create_fn, patch_fn)
        self.assertTrue(result)
        create_fn.assert_called_once()
        patch_fn.assert_not_called()

    def test_create_409_then_patch_succeeds(self):
        op = self._make_operator()
        create_fn = MagicMock(side_effect=_make_api_exception(409))
        patch_fn = MagicMock()
        result = op._apply_core_resource("TestResource", "ns", create_fn, patch_fn)
        self.assertTrue(result)
        create_fn.assert_called_once()
        patch_fn.assert_called_once()

    def test_create_409_then_patch_fails(self):
        op = self._make_operator()
        create_fn = MagicMock(side_effect=_make_api_exception(409))
        patch_fn = MagicMock(side_effect=_make_api_exception(500))
        result = op._apply_core_resource("TestResource", "ns", create_fn, patch_fn)
        self.assertFalse(result)

    def test_create_non_409_error(self):
        op = self._make_operator()
        create_fn = MagicMock(side_effect=_make_api_exception(403))
        patch_fn = MagicMock()
        result = op._apply_core_resource("TestResource", "ns", create_fn, patch_fn)
        self.assertFalse(result)
        patch_fn.assert_not_called()

    def test_unexpected_exception_returns_false(self):
        op = self._make_operator()
        create_fn = MagicMock(side_effect=ValueError("bad serialization"))
        patch_fn = MagicMock()
        result = op._apply_core_resource("TestResource", "ns", create_fn, patch_fn)
        self.assertFalse(result)
        patch_fn.assert_not_called()


class TestProvisionNamespaceResources(unittest.TestCase):
    """Tests for TeamsOperator.provision_namespace_resources()."""

    def _make_operator(self):
        with patch("teams_operator.config.load_incluster_config"), \
             patch("teams_operator.client.CoreV1Api") as mock_core, \
             patch("teams_operator.client.NetworkingV1Api") as mock_net, \
             patch("teams_operator.client.RbacAuthorizationV1Api") as mock_rbac:
            from teams_operator import TeamsOperator
            op = TeamsOperator()
            return op, mock_core.return_value, mock_net.return_value, mock_rbac.return_value

    def test_all_resources_created(self):
        op, core, net, rbac = self._make_operator()
        op.provision_namespace_resources("t1", "Team One", "team-team-one")

        core.create_namespaced_resource_quota.assert_called_once()
        core.create_namespaced_limit_range.assert_called_once()
        self.assertEqual(net.create_namespaced_network_policy.call_count, 4)
        core.create_namespaced_service_account.assert_called_once()
        rbac.create_namespaced_role_binding.assert_called_once()

    def test_partial_failure_continues(self):
        """If one resource fails, the rest should still be attempted."""
        op, core, net, rbac = self._make_operator()
        core.create_namespaced_resource_quota.side_effect = _make_api_exception(500)
        op.provision_namespace_resources("t1", "Team One", "team-team-one")

        # quota failed, but limit range + others still attempted
        core.create_namespaced_limit_range.assert_called_once()
        self.assertEqual(net.create_namespaced_network_policy.call_count, 4)
        core.create_namespaced_service_account.assert_called_once()
        rbac.create_namespaced_role_binding.assert_called_once()

    def test_409_triggers_patch(self):
        op, core, net, rbac = self._make_operator()
        core.create_namespaced_resource_quota.side_effect = _make_api_exception(409)
        op.provision_namespace_resources("t1", "Team One", "team-team-one")

        core.patch_namespaced_resource_quota.assert_called_once()


class TestCreateNamespaceAdmissionLabel(unittest.TestCase):
    """Verify create_namespace() includes the admission label."""

    def _make_operator(self):
        with patch("teams_operator.config.load_incluster_config"), \
             patch("teams_operator.client.CoreV1Api") as mock_core, \
             patch("teams_operator.client.NetworkingV1Api"), \
             patch("teams_operator.client.RbacAuthorizationV1Api"):
            from teams_operator import TeamsOperator
            op = TeamsOperator()
            return op, mock_core.return_value

    def test_namespace_has_admission_label(self):
        op, core = self._make_operator()
        op.create_namespace("t1", "Test", "team-test")
        body = core.create_namespace.call_args[1]["body"]
        self.assertEqual(body.metadata.labels["admission"], "true")

    def test_namespace_has_managed_by_label(self):
        op, core = self._make_operator()
        op.create_namespace("t1", "Test", "team-test")
        body = core.create_namespace.call_args[1]["body"]
        self.assertEqual(
            body.metadata.labels["app.kubernetes.io/managed-by"], "teams-operator"
        )


class TestReconcileTeamsEnrichment(unittest.TestCase):
    """Verify reconcile_teams() calls enrichment after namespace creation."""

    def _make_operator(self):
        with patch("teams_operator.config.load_incluster_config"), \
             patch("teams_operator.client.CoreV1Api"), \
             patch("teams_operator.client.NetworkingV1Api"), \
             patch("teams_operator.client.RbacAuthorizationV1Api"):
            from teams_operator import TeamsOperator
            op = TeamsOperator()
            return op

    def test_enrichment_called_on_new_team(self):
        op = self._make_operator()
        op.create_namespace = MagicMock(return_value=True)
        op.provision_namespace_resources = MagicMock()
        op.fetch_teams = MagicMock(return_value=[{"id": "t1", "name": "Alpha"}])

        # Make fetch_teams work as a coroutine
        async def _async_fetch():
            return [{"id": "t1", "name": "Alpha"}]
        op.fetch_teams = _async_fetch

        asyncio.run(op.reconcile_teams())
        op.provision_namespace_resources.assert_called_once_with(
            "t1", "Alpha", "team-alpha"
        )

    def test_enrichment_not_called_on_failure(self):
        op = self._make_operator()
        op.create_namespace = MagicMock(return_value=False)
        op.provision_namespace_resources = MagicMock()

        async def _async_fetch():
            return [{"id": "t1", "name": "Alpha"}]
        op.fetch_teams = _async_fetch

        asyncio.run(op.reconcile_teams())
        op.provision_namespace_resources.assert_not_called()

    def test_enrichment_called_for_existing_namespace_on_restart(self):
        """On restart, known_teams is empty so existing namespaces get re-enriched."""
        op = self._make_operator()
        # Simulate 409 (namespace already exists) → returns True
        exc = _make_api_exception(409)
        op.k8s_core_v1.create_namespace.side_effect = exc
        op.provision_namespace_resources = MagicMock()

        async def _async_fetch():
            return [{"id": "t1", "name": "Alpha"}]
        op.fetch_teams = _async_fetch

        asyncio.run(op.reconcile_teams())
        op.provision_namespace_resources.assert_called_once()


if __name__ == "__main__":
    unittest.main()
