"""Custom Agent CRUD API.

Endpoints for managing user-defined agent roles that extend the built-in
9 default agents. Custom agents are persisted in YAML config and participate
in debates alongside default agents.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from planagent.services.agent_registry import (
    create_custom_agent,
    delete_custom_agent,
    get_all_agent_configs,
    get_custom_agent,
    update_custom_agent,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Custom Agents"])


# ── Pydantic models ───────────────────────────────────────────────────


class CustomAgentCreate(BaseModel):
    """Create a new custom agent role."""

    name: str = Field(..., min_length=1, max_length=100)
    name_en: str = Field(default="", max_length=200)
    icon: str = Field(default="🤖", max_length=10)
    description: str = Field(..., min_length=1, max_length=5000)
    priority: int = Field(default=2, ge=1, le=2)
    recommended_models: list[str] | None = None


class CustomAgentUpdate(BaseModel):
    """Update an existing custom agent. All fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    name_en: str | None = Field(default=None, max_length=200)
    icon: str | None = Field(default=None, max_length=10)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    priority: int | None = Field(default=None, ge=1, le=2)
    recommended_models: list[str] | None = None


class AgentRead(BaseModel):
    """Read model for an agent (default or custom)."""

    role_key: str
    name: str
    name_en: str
    icon: str
    description: str
    recommended_models: list[str]
    priority: int
    is_custom: bool


# ── Helpers ────────────────────────────────────────────────────────────


def _agent_to_read(agent: Any) -> AgentRead:
    """Convert an AgentConfig to a read model."""
    return AgentRead(
        role_key=str(agent.role),
        name=agent.name,
        name_en=agent.name_en,
        icon=agent.icon,
        description=agent.description[:500] + ("..." if len(agent.description) > 500 else ""),
        recommended_models=agent.recommended_models,
        priority=agent.priority,
        is_custom=agent.is_custom,
    )


def _agent_to_read_full(agent: Any) -> dict[str, Any]:
    """Convert an AgentConfig to a full dict for detail views."""
    return {
        "role_key": str(agent.role),
        "name": agent.name,
        "name_en": agent.name_en,
        "icon": agent.icon,
        "description": agent.description,
        "recommended_models": agent.recommended_models,
        "priority": agent.priority,
        "is_custom": agent.is_custom,
    }


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/agents/all", response_model=list[AgentRead])
async def list_all_agents() -> list[AgentRead]:
    """List all agents (default + custom)."""
    agents = get_all_agent_configs()
    return [_agent_to_read(a) for a in agents]


@router.post("/agents/custom", response_model=dict[str, Any], status_code=201)
async def create_agent(body: CustomAgentCreate) -> dict[str, Any]:
    """Create a new custom agent role."""
    agent = create_custom_agent(
        name=body.name,
        name_en=body.name_en or body.name,
        icon=body.icon,
        description=body.description,
        priority=body.priority,
        recommended_models=body.recommended_models,
    )
    logger.info("Created custom agent: %s", agent.role)
    return _agent_to_read_full(agent)


@router.get("/agents/custom/{role_key}", response_model=dict[str, Any])
async def get_agent(role_key: str) -> dict[str, Any]:
    """Get a single custom agent by role_key."""
    agent = get_custom_agent(role_key)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Custom agent '{role_key}' not found")
    return _agent_to_read_full(agent)


@router.put("/agents/custom/{role_key}", response_model=dict[str, Any])
async def update_agent(role_key: str, body: CustomAgentUpdate) -> dict[str, Any]:
    """Update an existing custom agent."""
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    agent = update_custom_agent(role_key, **updates)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Custom agent '{role_key}' not found")

    logger.info("Updated custom agent: %s", role_key)
    return _agent_to_read_full(agent)


@router.delete("/agents/custom/{role_key}", status_code=204)
async def delete_agent(role_key: str) -> None:
    """Delete a custom agent role."""
    if not delete_custom_agent(role_key):
        raise HTTPException(status_code=404, detail=f"Custom agent '{role_key}' not found")
    logger.info("Deleted custom agent: %s", role_key)
