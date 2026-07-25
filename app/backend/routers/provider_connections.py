import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from dependencies.tenancy import EntityPolicy, filter_writes, get_current_workspace
from models.provider_connections import Provider_connections
from models.workspaces import Workspaces
from schemas.auth import UserResponse
from services.provider_connections import Provider_connectionsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/provider_connections", tags=["provider_connections"])

PROVIDER_CONNECTIONS_POLICY = EntityPolicy(
    model=Provider_connections,
    scope="workspace",
    writable=frozenset({"provider_type", "provider_name", "config_json"}),
    never_return=frozenset({"config_json"}),
)


# ---------- Pydantic Schemas ----------
class Provider_connectionsData(BaseModel):
    """Entity data schema (for create/update)"""
    workspace_id: int
    provider_type: str
    provider_name: str
    status: str = None
    config_json: str = None
    last_health_check: str = None
    error_count: int = None


class Provider_connectionsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    workspace_id: Optional[int] = None
    provider_type: Optional[str] = None
    provider_name: Optional[str] = None
    status: Optional[str] = None
    config_json: Optional[str] = None
    last_health_check: Optional[str] = None
    error_count: Optional[int] = None


class Provider_connectionsResponse(BaseModel):
    """Entity response schema

    config_json is intentionally absent: it holds provider credentials and
    must never be serialised into a response body. Removing the field here
    (rather than filtering it at runtime) means Pydantic has nowhere to put
    it, so no future route on this model can leak it by accident.
    """
    id: int
    workspace_id: int
    provider_type: str
    provider_name: str
    status: Optional[str] = None
    last_health_check: Optional[str] = None
    error_count: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Provider_connectionsListResponse(BaseModel):
    """List response schema"""
    items: List[Provider_connectionsResponse]
    total: int
    skip: int
    limit: int


class Provider_connectionsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Provider_connectionsData]


class Provider_connectionsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Provider_connectionsUpdateData


class Provider_connectionsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Provider_connectionsBatchUpdateItem]


class Provider_connectionsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Provider_connectionsListResponse)
async def query_provider_connectionss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Provider_connectionsService(db)
    query_dict = {}
    if query:
        try:
            query_dict = json.loads(query)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid query JSON format")
    query_dict["workspace_id"] = workspace.id
    return await service.get_list(skip=skip, limit=limit, query_dict=query_dict, sort=sort)


@router.get("/{id}", response_model=Provider_connectionsResponse)
async def get_provider_connections(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Provider_connectionsService(db)
    result = await service.get_by_id(id)
    if not result or result.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Not found")
    return result


@router.post("", response_model=Provider_connectionsResponse, status_code=201)
async def create_provider_connections(
    data: Provider_connectionsData,
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Provider_connectionsService(db)
    payload = filter_writes(data.model_dump(), PROVIDER_CONNECTIONS_POLICY, strict=False)
    payload["workspace_id"] = workspace.id
    result = await service.create(payload)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to create provider connection")
    return result


@router.post("/batch", response_model=List[Provider_connectionsResponse], status_code=201)
async def create_provider_connectionss_batch(
    request: Provider_connectionsBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=403, detail="Batch operations are not permitted on provider connections")


@router.put("/batch", response_model=List[Provider_connectionsResponse])
async def update_provider_connectionss_batch(
    request: Provider_connectionsBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=403, detail="Batch operations are not permitted on provider connections")


@router.put("/{id}", response_model=Provider_connectionsResponse)
async def update_provider_connections(
    id: int,
    data: Provider_connectionsUpdateData,
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Provider_connectionsService(db)
    existing = await service.get_by_id(id)
    if not existing or existing.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Not found")

    update_dict = filter_writes(data.model_dump(), PROVIDER_CONNECTIONS_POLICY, strict=True)
    if not update_dict:
        return existing
    return await service.update(id, update_dict)


@router.delete("/batch")
async def delete_provider_connectionss_batch(
    request: Provider_connectionsBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=403, detail="Batch operations are not permitted on provider connections")


@router.delete("/{id}")
async def delete_provider_connections(
    id: int,
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Provider_connectionsService(db)
    existing = await service.get_by_id(id)
    if not existing or existing.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Not found")
    await service.delete(id)
    return {"message": "Provider connection deleted", "id": id}
