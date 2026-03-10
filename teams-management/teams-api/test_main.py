"""Tests for the Teams API scaffolding feature."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from builders import (
    WorkloadType,
    build_cronjob,
    build_deployment,
    build_ingress,
    build_kustomization,
    build_service,
    build_staging_overlay,
    generate_workload_manifests,
    sanitize_namespace_name,
    sanitize_workload_name,
)
from github_client import GitHubClient
from main import app, teams_store

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_store():
    """Clear the in-memory store before each test."""
    teams_store.clear()
    yield
    teams_store.clear()


@pytest.fixture()
def team_id():
    """Create a team and return its ID."""
    resp = client.post("/teams", json={"name": "Backend Team"})
    assert resp.status_code == 200
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# TestSanitizeNamespaceName
# ---------------------------------------------------------------------------

class TestSanitizeNamespaceName:
    def test_simple_name(self):
        assert sanitize_namespace_name("backend") == "team-backend"

    def test_special_characters(self):
        assert sanitize_namespace_name("My Cool Team!") == "team-my-cool-team"

    def test_consecutive_hyphens(self):
        assert sanitize_namespace_name("a--b") == "team-a-b"

    def test_truncation(self):
        long_name = "a" * 100
        result = sanitize_namespace_name(long_name)
        assert len(result) <= 63
        assert result.startswith("team-")

    def test_leading_trailing_hyphens(self):
        assert sanitize_namespace_name("-test-") == "team-test"

    def test_uppercase(self):
        assert sanitize_namespace_name("MyTeam") == "team-myteam"


class TestSanitizeWorkloadName:
    def test_simple_name(self):
        assert sanitize_workload_name("checkout") == "checkout"

    def test_special_characters(self):
        assert sanitize_workload_name("my_service!v2") == "my-service-v2"

    def test_truncation(self):
        result = sanitize_workload_name("a" * 100)
        assert len(result) <= 63


# ---------------------------------------------------------------------------
# TestSecurityContexts
# ---------------------------------------------------------------------------

class TestSecurityContexts:
    def test_pod_security_context_run_as_non_root(self):
        from builders import _pod_security_context
        ctx = _pod_security_context()
        assert ctx["runAsNonRoot"] is True

    def test_pod_security_context_run_as_user(self):
        from builders import _pod_security_context
        ctx = _pod_security_context()
        assert ctx["runAsUser"] == 1000
        assert ctx["runAsUser"] != 0

    def test_pod_security_context_seccomp(self):
        from builders import _pod_security_context
        ctx = _pod_security_context()
        assert ctx["seccompProfile"]["type"] == "RuntimeDefault"

    def test_container_security_context_privilege_escalation(self):
        from builders import _container_security_context
        ctx = _container_security_context()
        assert ctx["allowPrivilegeEscalation"] is False

    def test_container_security_context_read_only_root(self):
        from builders import _container_security_context
        ctx = _container_security_context()
        assert ctx["readOnlyRootFilesystem"] is True

    def test_container_security_context_drop_capabilities(self):
        from builders import _container_security_context
        ctx = _container_security_context()
        assert ctx["capabilities"]["drop"] == ["ALL"]


# ---------------------------------------------------------------------------
# TestBuildDeployment
# ---------------------------------------------------------------------------

class TestBuildDeployment:
    def test_kind(self):
        d = build_deployment("svc", "team", WorkloadType.web)
        assert d["kind"] == "Deployment"
        assert d["apiVersion"] == "apps/v1"

    def test_labels(self):
        d = build_deployment("svc", "team", WorkloadType.web)
        labels = d["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "svc"
        assert labels["app.kubernetes.io/managed-by"] == "teams-scaffolder"

    def test_commit_sha_annotation(self):
        d = build_deployment("svc", "team", WorkloadType.web)
        assert d["metadata"]["annotations"]["commit-sha"] == "REPLACE_ME"

    def test_web_has_ports(self):
        d = build_deployment("svc", "team", WorkloadType.web, port=3000)
        container = d["spec"]["template"]["spec"]["containers"][0]
        assert container["ports"] == [{"containerPort": 3000}]

    def test_web_has_http_probes(self):
        d = build_deployment("svc", "team", WorkloadType.web, port=8080)
        container = d["spec"]["template"]["spec"]["containers"][0]
        assert container["livenessProbe"]["httpGet"]["port"] == 8080
        assert container["readinessProbe"]["httpGet"]["port"] == 8080

    def test_worker_has_no_ports(self):
        d = build_deployment("svc", "team", WorkloadType.worker)
        container = d["spec"]["template"]["spec"]["containers"][0]
        assert "ports" not in container

    def test_worker_has_exec_probes(self):
        d = build_deployment("svc", "team", WorkloadType.worker)
        container = d["spec"]["template"]["spec"]["containers"][0]
        assert "exec" in container["livenessProbe"]

    def test_security_context_present(self):
        d = build_deployment("svc", "team", WorkloadType.web)
        pod_sc = d["spec"]["template"]["spec"]["securityContext"]
        assert pod_sc["runAsNonRoot"] is True
        container_sc = d["spec"]["template"]["spec"]["containers"][0]["securityContext"]
        assert container_sc["allowPrivilegeEscalation"] is False

    def test_resource_requirements(self):
        d = build_deployment("svc", "team", WorkloadType.web)
        res = d["spec"]["template"]["spec"]["containers"][0]["resources"]
        assert res["requests"]["cpu"] == "50m"
        assert res["limits"]["memory"] == "256Mi"


# ---------------------------------------------------------------------------
# TestBuildService
# ---------------------------------------------------------------------------

class TestBuildService:
    def test_kind(self):
        s = build_service("svc", "team")
        assert s["kind"] == "Service"

    def test_selector(self):
        s = build_service("svc", "team")
        assert s["spec"]["selector"]["app.kubernetes.io/name"] == "svc"

    def test_port_config(self):
        s = build_service("svc", "team", port=3000)
        port_spec = s["spec"]["ports"][0]
        assert port_spec["port"] == 3000
        assert port_spec["targetPort"] == 3000

    def test_cluster_ip_type(self):
        s = build_service("svc", "team")
        assert s["spec"]["type"] == "ClusterIP"


# ---------------------------------------------------------------------------
# TestBuildIngress
# ---------------------------------------------------------------------------

class TestBuildIngress:
    def test_kind(self):
        i = build_ingress("svc", "team")
        assert i["kind"] == "Ingress"

    def test_host_format(self):
        i = build_ingress("checkout", "team")
        host = i["spec"]["rules"][0]["host"]
        assert host == "checkout.kube-playground.io"

    def test_traefik_class(self):
        i = build_ingress("svc", "team")
        assert i["spec"]["ingressClassName"] == "traefik"

    def test_backend_reference(self):
        i = build_ingress("svc", "team", port=9090)
        backend = i["spec"]["rules"][0]["http"]["paths"][0]["backend"]
        assert backend["service"]["name"] == "svc"
        assert backend["service"]["port"]["number"] == 9090

    def test_tls_config(self):
        i = build_ingress("svc", "team")
        tls = i["spec"]["tls"][0]
        assert "svc.kube-playground.io" in tls["hosts"]
        assert tls["secretName"] == "star-kube-playground-io-tls"


# ---------------------------------------------------------------------------
# TestBuildCronjob
# ---------------------------------------------------------------------------

class TestBuildCronjob:
    def test_kind(self):
        cj = build_cronjob("job", "team")
        assert cj["kind"] == "CronJob"
        assert cj["apiVersion"] == "batch/v1"

    def test_schedule(self):
        cj = build_cronjob("job", "team")
        assert cj["spec"]["schedule"] == "*/15 * * * *"

    def test_custom_schedule(self):
        cj = build_cronjob("job", "team", schedule="0 * * * *")
        assert cj["spec"]["schedule"] == "0 * * * *"

    def test_restart_policy(self):
        cj = build_cronjob("job", "team")
        pod_spec = cj["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        assert pod_spec["restartPolicy"] == "OnFailure"

    def test_security_contexts(self):
        cj = build_cronjob("job", "team")
        pod_spec = cj["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        assert pod_spec["securityContext"]["runAsNonRoot"] is True
        container_sc = pod_spec["containers"][0]["securityContext"]
        assert container_sc["allowPrivilegeEscalation"] is False
        assert container_sc["capabilities"]["drop"] == ["ALL"]


# ---------------------------------------------------------------------------
# TestBuildKustomization
# ---------------------------------------------------------------------------

class TestBuildKustomization:
    def test_resources_list(self):
        k = build_kustomization(["deployment.yaml", "service.yaml"])
        assert k["kind"] == "Kustomization"
        assert "deployment.yaml" in k["resources"]
        assert "service.yaml" in k["resources"]

    def test_resources_sorted(self):
        k = build_kustomization(["service.yaml", "deployment.yaml"])
        assert k["resources"] == ["deployment.yaml", "service.yaml"]


# ---------------------------------------------------------------------------
# TestBuildStagingOverlay
# ---------------------------------------------------------------------------

class TestBuildStagingOverlay:
    def test_namespace(self):
        o = build_staging_overlay("checkout", "team-backend")
        assert o["namespace"] == "team-backend"

    def test_resource_reference(self):
        o = build_staging_overlay("checkout", "team-backend")
        assert o["resources"] == ["../../base/checkout"]


# ---------------------------------------------------------------------------
# TestGenerateWorkloadManifests
# ---------------------------------------------------------------------------

class TestGenerateWorkloadManifests:
    def test_web_file_count(self):
        manifests = generate_workload_manifests("svc", "team", WorkloadType.web)
        assert len(manifests) == 4  # deployment, service, ingress, kustomization
        filenames = [m.filename for m in manifests]
        assert "deployment.yaml" in filenames
        assert "service.yaml" in filenames
        assert "ingress.yaml" in filenames
        assert "kustomization.yaml" in filenames

    def test_worker_file_count(self):
        manifests = generate_workload_manifests("svc", "team", WorkloadType.worker)
        assert len(manifests) == 2  # deployment, kustomization

    def test_cronjob_file_count(self):
        manifests = generate_workload_manifests("svc", "team", WorkloadType.cronjob)
        assert len(manifests) == 2  # cronjob, kustomization

    def test_kustomization_references_all_files(self):
        manifests = generate_workload_manifests("svc", "team", WorkloadType.web)
        kustomization = next(m for m in manifests if m.filename == "kustomization.yaml")
        resource_filenames = [m.filename for m in manifests if m.filename != "kustomization.yaml"]
        for f in resource_filenames:
            assert f in kustomization.content["resources"]


# ---------------------------------------------------------------------------
# TestGatekeeperCompliance
# ---------------------------------------------------------------------------

class TestGatekeeperCompliance:
    """Verify generated manifests satisfy each Gatekeeper policy."""

    def test_root_prevention_deployment(self):
        """RootPrevention: runAsNonRoot=true, runAsUser!=0, no privileged, no escalation."""
        d = build_deployment("svc", "team", WorkloadType.web)
        pod_sc = d["spec"]["template"]["spec"]["securityContext"]
        assert pod_sc["runAsNonRoot"] is True
        assert pod_sc["runAsUser"] != 0

        container_sc = d["spec"]["template"]["spec"]["containers"][0]["securityContext"]
        assert container_sc["allowPrivilegeEscalation"] is False
        assert "privileged" not in container_sc

    def test_root_prevention_cronjob(self):
        cj = build_cronjob("job", "team")
        pod_spec = cj["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        assert pod_spec["securityContext"]["runAsNonRoot"] is True
        assert pod_spec["securityContext"]["runAsUser"] != 0
        assert pod_spec["containers"][0]["securityContext"]["allowPrivilegeEscalation"] is False

    def test_code_coverage_annotation(self):
        """CodeCoverageSimple: Deployment must have commit-sha annotation."""
        d = build_deployment("svc", "team", WorkloadType.web)
        assert "commit-sha" in d["metadata"]["annotations"]

    def test_code_coverage_not_on_cronjob(self):
        """CronJobs are not Deployments — no commit-sha required."""
        cj = build_cronjob("job", "team")
        assert "annotations" not in cj["metadata"] or "commit-sha" not in cj["metadata"].get(
            "annotations", {}
        )

    def test_cve_scanning_image_placeholder(self):
        """VulnerabilityScan: image uses REPLACE_ME placeholder for user to set."""
        d = build_deployment("svc", "team", WorkloadType.web)
        image = d["spec"]["template"]["spec"]["containers"][0]["image"]
        assert image.startswith("REPLACE_ME/")

    def test_security_capabilities_dropped(self):
        """All capabilities dropped for both Deployment and CronJob containers."""
        d = build_deployment("svc", "team", WorkloadType.web)
        caps = d["spec"]["template"]["spec"]["containers"][0]["securityContext"]["capabilities"]
        assert caps["drop"] == ["ALL"]

        cj = build_cronjob("job", "team")
        caps = cj["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0][
            "securityContext"
        ]["capabilities"]
        assert caps["drop"] == ["ALL"]


# ---------------------------------------------------------------------------
# TestScaffoldEndpoint
# ---------------------------------------------------------------------------

class TestScaffoldEndpoint:
    def test_404_for_missing_team(self):
        resp = client.post(
            "/teams/nonexistent/workloads",
            json={"name": "svc", "type": "web"},
        )
        assert resp.status_code == 404

    def test_422_for_invalid_type(self):
        resp = client.post("/teams", json={"name": "Team"})
        team_id = resp.json()["id"]
        resp = client.post(
            f"/teams/{team_id}/workloads",
            json={"name": "svc", "type": "invalid"},
        )
        assert resp.status_code == 422

    @patch.dict("os.environ", {"GITHUB_TOKEN": "", "GITHUB_REPO": ""}, clear=False)
    def test_web_scaffold_without_github(self, team_id):
        resp = client.post(
            f"/teams/{team_id}/workloads",
            json={"name": "checkout", "type": "web", "port": 8080},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["workload_name"] == "checkout"
        assert data["workload_type"] == "web"
        assert data["namespace"] == "team-backend-team"
        assert data["branch"] == "scaffold/checkout"
        assert data["pr_url"] is None
        assert len(data["manifests"]) == 4

    @patch.dict("os.environ", {"GITHUB_TOKEN": "", "GITHUB_REPO": ""}, clear=False)
    def test_worker_scaffold_without_github(self, team_id):
        resp = client.post(
            f"/teams/{team_id}/workloads",
            json={"name": "processor", "type": "worker"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["workload_type"] == "worker"
        assert len(data["manifests"]) == 2

    @patch.dict("os.environ", {"GITHUB_TOKEN": "", "GITHUB_REPO": ""}, clear=False)
    def test_cronjob_scaffold_without_github(self, team_id):
        resp = client.post(
            f"/teams/{team_id}/workloads",
            json={"name": "cleanup", "type": "cronjob"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["workload_type"] == "cronjob"
        assert len(data["manifests"]) == 2

    @patch.dict("os.environ", {"GITHUB_TOKEN": "", "GITHUB_REPO": ""}, clear=False)
    def test_response_includes_team_info(self, team_id):
        resp = client.post(
            f"/teams/{team_id}/workloads",
            json={"name": "svc", "type": "web"},
        )
        data = resp.json()
        assert data["team_id"] == team_id
        assert data["team_name"] == "Backend Team"

    @patch.dict("os.environ", {"GITHUB_TOKEN": "", "GITHUB_REPO": ""}, clear=False)
    def test_workload_name_sanitized(self, team_id):
        resp = client.post(
            f"/teams/{team_id}/workloads",
            json={"name": "My Service!!!", "type": "web"},
        )
        data = resp.json()
        assert data["workload_name"] == "my-service"

    @patch.dict("os.environ", {"GITHUB_TOKEN": "", "GITHUB_REPO": ""}, clear=False)
    def test_default_port(self, team_id):
        resp = client.post(
            f"/teams/{team_id}/workloads",
            json={"name": "svc", "type": "web"},
        )
        data = resp.json()
        deployment = next(
            m for m in data["manifests"] if m["filename"] == "deployment.yaml"
        )
        container = deployment["content"]["spec"]["template"]["spec"]["containers"][0]
        assert container["ports"][0]["containerPort"] == 8080


# ---------------------------------------------------------------------------
# TestGitHubClient
# ---------------------------------------------------------------------------

class TestGitHubClient:
    def setup_method(self):
        self.gh = GitHubClient("fake-token", "owner/repo")

    @patch("github_client.http_requests.get")
    def test_get_default_branch_sha(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"object": {"sha": "abc123"}},
            raise_for_status=lambda: None,
        )
        sha = self.gh.get_default_branch_sha()
        assert sha == "abc123"
        mock_get.assert_called_once()

    @patch("github_client.http_requests.post")
    def test_create_branch(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=201, raise_for_status=lambda: None
        )
        self.gh.create_branch("scaffold/test", "abc123")
        mock_post.assert_called_once()
        call_json = mock_post.call_args[1]["json"]
        assert call_json["ref"] == "refs/heads/scaffold/test"
        assert call_json["sha"] == "abc123"

    @patch("github_client.http_requests.get")
    @patch("github_client.http_requests.put")
    def test_create_or_update_file_new(self, mock_put, mock_get):
        mock_get.return_value = MagicMock(status_code=404)
        mock_put.return_value = MagicMock(
            status_code=201, raise_for_status=lambda: None
        )
        self.gh.create_or_update_file("branch", "path/file.yaml", "content", "msg")
        mock_put.assert_called_once()
        call_json = mock_put.call_args[1]["json"]
        assert "sha" not in call_json

    @patch("github_client.http_requests.get")
    @patch("github_client.http_requests.put")
    def test_create_or_update_file_existing(self, mock_put, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"sha": "existing-sha"},
            raise_for_status=lambda: None,
        )
        mock_put.return_value = MagicMock(
            status_code=200, raise_for_status=lambda: None
        )
        self.gh.create_or_update_file("branch", "path/file.yaml", "content", "msg")
        call_json = mock_put.call_args[1]["json"]
        assert call_json["sha"] == "existing-sha"

    @patch("github_client.http_requests.get")
    def test_get_file_content_exists(self, mock_get):
        import base64

        encoded = base64.b64encode(b"hello world").decode()
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"content": encoded},
            raise_for_status=lambda: None,
        )
        content = self.gh.get_file_content("branch", "file.yaml")
        assert content == "hello world"

    @patch("github_client.http_requests.get")
    def test_get_file_content_not_found(self, mock_get):
        mock_get.return_value = MagicMock(status_code=404)
        content = self.gh.get_file_content("branch", "file.yaml")
        assert content is None

    @patch("github_client.http_requests.post")
    def test_create_pull_request(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=201,
            json=lambda: {"html_url": "https://github.com/owner/repo/pull/1"},
            raise_for_status=lambda: None,
        )
        url = self.gh.create_pull_request("branch", "title", "body")
        assert url == "https://github.com/owner/repo/pull/1"
        call_json = mock_post.call_args[1]["json"]
        assert call_json["base"] == "main"
        assert call_json["head"] == "branch"


# ---------------------------------------------------------------------------
# TestExistingEndpoints (regression)
# ---------------------------------------------------------------------------

class TestExistingEndpoints:
    def test_root(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Teams API is running"

    def test_health(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_create_and_get_team(self):
        resp = client.post("/teams", json={"name": "Test"})
        assert resp.status_code == 200
        team_id = resp.json()["id"]

        resp = client.get(f"/teams/{team_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test"

    def test_duplicate_team_name(self):
        client.post("/teams", json={"name": "Unique"})
        resp = client.post("/teams", json={"name": "unique"})
        assert resp.status_code == 400

    def test_delete_team(self):
        resp = client.post("/teams", json={"name": "DeleteMe"})
        team_id = resp.json()["id"]
        resp = client.delete(f"/teams/{team_id}")
        assert resp.status_code == 200

    def test_get_nonexistent_team(self):
        resp = client.get("/teams/nonexistent")
        assert resp.status_code == 404
