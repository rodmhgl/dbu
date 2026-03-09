#!/usr/bin/env python3
"""
Teams Operator - Creates Kubernetes namespaces when teams are created in the Teams API
"""

import asyncio
import logging
import os
from typing import Set, Dict
import aiohttp
from kubernetes import client, config
from kubernetes.client.rest import ApiException

from resources import (
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('teams-operator')

class TeamsOperator:
    def __init__(self):
        self.teams_api_url = os.getenv('TEAMS_API_URL', 'http://teams-api-service:80')
        self.poll_interval = int(os.getenv('POLL_INTERVAL', '30'))  # seconds
        self.known_teams: Set[str] = set()
        self.team_namespaces: Dict[str, str] = {}
        
        # Initialize Kubernetes client
        try:
            # Try in-cluster config first (when running in pod)
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            # Fall back to local kubeconfig (for development)
            config.load_kube_config()
            logger.info("Loaded local kubeconfig")
        
        self.k8s_core_v1 = client.CoreV1Api()
        self.k8s_networking_v1 = client.NetworkingV1Api()
        self.k8s_rbac_v1 = client.RbacAuthorizationV1Api()

    def sanitize_namespace_name(self, team_name: str) -> str:
        """Convert team name to valid Kubernetes namespace name"""
        # Lowercase, replace spaces/special chars with hyphens, remove consecutive hyphens
        namespace = team_name.lower()
        namespace = ''.join(c if c.isalnum() else '-' for c in namespace)
        namespace = '-'.join(filter(None, namespace.split('-')))  # Remove consecutive hyphens
        
        # Ensure it starts and ends with alphanumeric
        namespace = namespace.strip('-')
        
        # Kubernetes namespace names must be <= 63 characters
        if len(namespace) > 63:
            namespace = namespace[:63].rstrip('-')
            
        # Add prefix to avoid conflicts
        namespace = f"team-{namespace}"
        
        return namespace
    
    async def fetch_teams(self) -> list:
        """Fetch current teams from the Teams API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.teams_api_url}/teams") as response:
                    if response.status == 200:
                        teams = await response.json()
                        logger.debug(f"Fetched {len(teams)} teams from API")
                        return teams
                    else:
                        logger.error(f"Failed to fetch teams: HTTP {response.status}")
                        return []
        except aiohttp.ClientError as e:
            logger.error(f"Error connecting to Teams API: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching teams: {e}")
            return []
    
    def create_namespace(self, team_id: str, team_name: str, namespace_name: str) -> bool:
        """Create a Kubernetes namespace for the team"""
        try:
            # Define namespace metadata
            namespace_body = client.V1Namespace(
                metadata=client.V1ObjectMeta(
                    name=namespace_name,
                    labels={
                        "admission": "true",
                        "app.kubernetes.io/managed-by": "teams-operator",
                        "teams.example.com/team-id": team_id,
                        "teams.example.com/team-name": sanitize_label_value(team_name),
                    },
                    annotations={
                        "teams.example.com/original-team-name": team_name,
                        "teams.example.com/created-by": "teams-operator",
                        "teams.example.com/team-id": team_id
                    }
                )
            )
            
            # Create the namespace
            self.k8s_core_v1.create_namespace(body=namespace_body)
            logger.info(f"✅ Created namespace '{namespace_name}' for team '{team_name}' (ID: {team_id})")
            return True
            
        except ApiException as e:
            if e.status == 409:  # Namespace already exists
                logger.warning(f"⚠️ Namespace '{namespace_name}' already exists")
                return True
            else:
                logger.error(f"❌ Failed to create namespace '{namespace_name}': {e}")
                return False
        except Exception as e:
            logger.error(f"❌ Unexpected error creating namespace: {e}")
            return False
    
    def delete_namespace(self, namespace_name: str, team_name: str) -> bool:
        """Delete a Kubernetes namespace when team is removed"""
        try:
            self.k8s_core_v1.delete_namespace(name=namespace_name)
            logger.info(f"🗑️ Deleted namespace '{namespace_name}' for removed team '{team_name}'")
            return True
        except ApiException as e:
            if e.status == 404:  # Namespace doesn't exist
                logger.warning(f"⚠️ Namespace '{namespace_name}' not found (already deleted?)")
                return True
            else:
                logger.error(f"❌ Failed to delete namespace '{namespace_name}': {e}")
                return False
        except Exception as e:
            logger.error(f"❌ Unexpected error deleting namespace: {e}")
            return False
    
    def _apply_core_resource(
        self,
        resource_name: str,
        namespace_name: str,
        create_fn,
        patch_fn,
    ) -> bool:
        """Idempotent create-or-patch for a single resource."""
        try:
            create_fn()
            logger.info(f"  ✅ Created {resource_name} in '{namespace_name}'")
            return True
        except ApiException as e:
            if e.status == 409:
                try:
                    patch_fn()
                    logger.info(f"  🔄 Patched existing {resource_name} in '{namespace_name}'")
                    return True
                except ApiException as patch_err:
                    logger.error(
                        f"  ❌ Failed to patch {resource_name} in '{namespace_name}': {patch_err}"
                    )
                    return False
            else:
                logger.error(
                    f"  ❌ Failed to create {resource_name} in '{namespace_name}': {e}"
                )
                return False

    def provision_namespace_resources(
        self, team_id: str, team_name: str, namespace_name: str
    ) -> None:
        """Apply all enrichment resources to a team namespace."""
        logger.info(f"🔧 Provisioning enrichment resources for '{namespace_name}'")

        # --- ResourceQuota ---
        quota = build_resource_quota(namespace_name, team_id, team_name)
        self._apply_core_resource(
            "ResourceQuota", namespace_name,
            lambda: self.k8s_core_v1.create_namespaced_resource_quota(namespace_name, quota),
            lambda: self.k8s_core_v1.patch_namespaced_resource_quota("team-quota", namespace_name, quota),
        )

        # --- LimitRange ---
        lr = build_limit_range(namespace_name, team_id, team_name)
        self._apply_core_resource(
            "LimitRange", namespace_name,
            lambda: self.k8s_core_v1.create_namespaced_limit_range(namespace_name, lr),
            lambda: self.k8s_core_v1.patch_namespaced_limit_range("team-limits", namespace_name, lr),
        )

        # --- NetworkPolicies ---
        netpol_builders = [
            ("deny-all-ingress", build_network_policy_deny_ingress),
            ("allow-same-namespace", build_network_policy_allow_same_ns),
            ("allow-prometheus-scrape", build_network_policy_allow_prometheus),
            ("allow-ingress-controller", build_network_policy_allow_ingress_controller),
        ]
        for np_name, builder in netpol_builders:
            body = builder(namespace_name, team_id, team_name)
            self._apply_core_resource(
                f"NetworkPolicy/{np_name}", namespace_name,
                lambda b=body: self.k8s_networking_v1.create_namespaced_network_policy(namespace_name, b),
                lambda b=body: self.k8s_networking_v1.patch_namespaced_network_policy(np_name, namespace_name, b),
            )

        # --- ServiceAccount ---
        sa = build_service_account(namespace_name, team_id, team_name)
        self._apply_core_resource(
            "ServiceAccount/team-deployer", namespace_name,
            lambda: self.k8s_core_v1.create_namespaced_service_account(namespace_name, sa),
            lambda: self.k8s_core_v1.patch_namespaced_service_account("team-deployer", namespace_name, sa),
        )

        # --- RoleBinding ---
        rb = build_role_binding(namespace_name, team_id, team_name)
        self._apply_core_resource(
            "RoleBinding/team-edit-binding", namespace_name,
            lambda: self.k8s_rbac_v1.create_namespaced_role_binding(namespace_name, rb),
            lambda: self.k8s_rbac_v1.patch_namespaced_role_binding("team-edit-binding", namespace_name, rb),
        )

        logger.info(f"🔧 Enrichment provisioning complete for '{namespace_name}'")

    async def reconcile_teams(self):
        """Main reconciliation loop - sync teams with namespaces"""
        teams = await self.fetch_teams()
        current_teams = {team['id']: team for team in teams}
        current_team_ids = set(current_teams.keys())
        
        # Handle new teams (create namespaces)
        new_teams = current_team_ids - self.known_teams
        for team_id in new_teams:
            team = current_teams[team_id]
            team_name = team['name']
            namespace_name = self.sanitize_namespace_name(team_name)
            
            if self.create_namespace(team_id, team_name, namespace_name):
                self.provision_namespace_resources(team_id, team_name, namespace_name)
                self.team_namespaces[team_id] = namespace_name
        
        # Handle deleted teams (remove namespaces)
        deleted_teams = self.known_teams - current_team_ids
        for team_id in deleted_teams:
            if team_id in self.team_namespaces:
                namespace_name = self.team_namespaces[team_id]
                # Get team name from namespace annotations if possible
                team_name = f"team-{team_id}"  # fallback
                
                if self.delete_namespace(namespace_name, team_name):
                    del self.team_namespaces[team_id]
        
        # Update known teams
        self.known_teams = current_team_ids
        
        if new_teams or deleted_teams:
            logger.info(f"📊 Reconciliation complete: {len(current_teams)} teams, {len(self.team_namespaces)} namespaces")
    
    async def run(self):
        """Main operator loop"""
        logger.info(f"🚀 Teams Operator starting...")
        logger.info(f"📡 Teams API URL: {self.teams_api_url}")
        logger.info(f"⏰ Poll interval: {self.poll_interval} seconds")
        
        # Initial reconciliation
        await self.reconcile_teams()
        
        # Main loop
        while True:
            try:
                await asyncio.sleep(self.poll_interval)
                await self.reconcile_teams()
            except KeyboardInterrupt:
                logger.info("👋 Received shutdown signal, exiting...")
                break
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}")
                await asyncio.sleep(self.poll_interval)

async def main():
    """Entry point"""
    operator = TeamsOperator()
    await operator.run()

if __name__ == "__main__":
    asyncio.run(main())
