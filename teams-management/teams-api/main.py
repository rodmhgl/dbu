import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from builders import (
    WorkloadCreate,
    WorkloadScaffoldResponse,
    build_staging_overlay,
    generate_workload_manifests,
    sanitize_namespace_name,
    sanitize_workload_name,
)
from github_client import GitHubClient

app = FastAPI(
    title="Teams API",
    description="A simple API for team leads to create and manage teams",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_headers=["*"],
    allow_methods=["*"],
    allow_origins=["*"],
)

# In-memory storage
teams_store: Dict[str, Dict] = {}

# GitHub configuration (optional — scaffold works without it)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")


# ---------------------------------------------------------------------------
# Pydantic models — team CRUD
# ---------------------------------------------------------------------------

class TeamCreate(BaseModel):
    name: str


class Team(BaseModel):
    created_at: datetime
    id: str
    name: str


# ---------------------------------------------------------------------------
# API endpoints — team CRUD
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {"message": "Teams API is running"}


@app.post("/teams", response_model=Team)
async def create_team(team: TeamCreate):
    """Create a new team"""
    for existing_team in teams_store.values():
        if existing_team["name"].lower() == team.name.lower():
            raise HTTPException(status_code=400, detail="Team name already exists")

    team_id = str(uuid.uuid4())
    new_team = {
        "created_at": datetime.now(),
        "id": team_id,
        "name": team.name,
    }

    teams_store[team_id] = new_team
    return Team(**new_team)


@app.get("/teams", response_model=List[Team])
async def get_teams():
    """Get all teams"""
    return [Team(**team) for team in teams_store.values()]


@app.get("/teams/{team_id}", response_model=Team)
async def get_team(team_id: str):
    """Get a specific team by ID"""
    if team_id not in teams_store:
        raise HTTPException(status_code=404, detail="Team not found")

    return Team(**teams_store[team_id])


@app.delete("/teams/{team_id}")
async def delete_team(team_id: str):
    """Delete a team"""
    if team_id not in teams_store:
        raise HTTPException(status_code=404, detail="Team not found")

    deleted_team = teams_store.pop(team_id)
    return {"message": f"Team '{deleted_team['name']}' deleted successfully"}


@app.get("/health")
async def health_check():
    """Health check endpoint for Kubernetes"""
    return {"status": "healthy", "teams_count": len(teams_store)}


# ---------------------------------------------------------------------------
# Scaffold endpoint
# ---------------------------------------------------------------------------

@app.post("/teams/{team_id}/workloads", response_model=WorkloadScaffoldResponse)
async def scaffold_workload(team_id: str, workload: WorkloadCreate):
    """Generate Gatekeeper-compliant K8s manifests, push to a Git branch, and open a PR."""
    if team_id not in teams_store:
        raise HTTPException(status_code=404, detail="Team not found")

    team = teams_store[team_id]
    team_name = team["name"]
    namespace = sanitize_namespace_name(team_name)
    workload_name = sanitize_workload_name(workload.name)

    manifests = generate_workload_manifests(
        workload_name=workload_name,
        team_name=team_name,
        workload_type=workload.type,
        port=workload.port or 8080,
    )

    branch = f"scaffold/{workload_name}"
    pr_url: Optional[str] = None

    if GITHUB_TOKEN and GITHUB_REPO:
        gh = GitHubClient(GITHUB_TOKEN, GITHUB_REPO)

        sha = gh.get_default_branch_sha()
        gh.create_branch(branch, sha)

        for manifest in manifests:
            file_path = f"apps/base/{workload_name}/{manifest.filename}"
            content = yaml.dump(manifest.content, default_flow_style=False, sort_keys=True)
            gh.create_or_update_file(
                branch=branch,
                path=file_path,
                content=content,
                message=f"scaffold({workload_name}): add {manifest.filename}",
            )

        staging_overlay = build_staging_overlay(workload_name, namespace)
        staging_overlay_content = yaml.dump(
            staging_overlay, default_flow_style=False, sort_keys=True
        )
        gh.create_or_update_file(
            branch=branch,
            path=f"apps/staging/{workload_name}/kustomization.yaml",
            content=staging_overlay_content,
            message=f"scaffold({workload_name}): add staging overlay",
        )

        existing_kustomization = gh.get_file_content(branch, "apps/staging/kustomization.yaml")
        if existing_kustomization:
            kustomization_data = yaml.safe_load(existing_kustomization)
            resources = kustomization_data.get("resources", [])
            new_ref = f"./{workload_name}"
            if new_ref not in resources:
                resources.append(new_ref)
                resources.sort()
                kustomization_data["resources"] = resources
                updated_content = yaml.dump(
                    kustomization_data, default_flow_style=False, sort_keys=True
                )
                gh.create_or_update_file(
                    branch=branch,
                    path="apps/staging/kustomization.yaml",
                    content=updated_content,
                    message=f"scaffold({workload_name}): register in staging kustomization",
                )

        pr_url = gh.create_pull_request(
            branch=branch,
            title=f"scaffold: add {workload_name} ({workload.type.value})",
            body=(
                f"## Workload Scaffold\n\n"
                f"- **Team:** {team_name}\n"
                f"- **Namespace:** {namespace}\n"
                f"- **Workload:** {workload_name}\n"
                f"- **Type:** {workload.type.value}\n\n"
                f"Generated by teams-api scaffolder.\n\n"
                f"### Next steps\n"
                f"1. Replace `REPLACE_ME` image with your container image\n"
                f"2. Update `commit-sha` annotation with your build SHA\n"
                f"3. Merge to deploy via Flux\n"
            ),
        )

    return WorkloadScaffoldResponse(
        branch=branch,
        manifests=manifests,
        namespace=namespace,
        pr_url=pr_url,
        team_id=team_id,
        team_name=team_name,
        workload_name=workload_name,
        workload_type=workload.type,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
