import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.workspace_members import Workspace_membersService
from dependencies.auth import get_current_user
from dependencies.tenancy import get_current_workspace
from models.workspaces import Workspaces
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/workspace_members", tags=["workspace_members"])


# ---------- Pydantic Schemas ----------
class Workspace_membersData(BaseModel):
    """Entity data schema (for create/update)"""
    workspace_id: int
    role: Optional[str] = None
    invited_email: Optional[str] = None
    status: Optional[str] = None
class Workspace_membersUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    workspace_id: Optional[int] = None
    role: Optional[str] = None
    invited_email: Optional[str] = None
    status: Optional[str] = None


class Workspace_membersResponse(BaseModel):
    """Entity response schema"""
    id: int
    workspace_id: int
    role: Optional[str] = None
    invited_email: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Workspace_membersListResponse(BaseModel):
    """List response schema"""
    items: List[Workspace_membersResponse]
    total: int
    skip: int
    limit: int


class Workspace_membersBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Workspace_membersData]


class Workspace_membersBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Workspace_membersUpdateData


class Workspace_membersBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Workspace_membersBatchUpdateItem]


class Workspace_membersBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Workspace_membersListResponse)
async def query_workspace_memberss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Workspace_membersService(db)
    query_dict = {}
    if query:
        try:
            query_dict = json.loads(query)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid query JSON format")
    query_dict["workspace_id"] = workspace.id
    return await service.get_list(skip=skip, limit=limit, query_dict=query_dict, sort=sort)


@router.get("/{id}", response_model=Workspace_membersResponse)
async def get_workspace_members(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Workspace_membersService(db)
    result = await service.get_by_id(id)
    if not result or result.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Not found")
    return result


@router.post("", response_model=Workspace_membersResponse, status_code=201)
async def create_workspace_members(
    data: Workspace_membersData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new workspace_members"""
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )


@router.post("/batch", response_model=List[Workspace_membersResponse], status_code=201)
async def create_workspace_memberss_batch(
    request: Workspace_membersBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple workspace_memberss in a single request"""
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )


@router.put("/batch", response_model=List[Workspace_membersResponse])
async def update_workspace_memberss_batch(
    request: Workspace_membersBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple workspace_memberss in a single request"""
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )


@router.put("/{id}", response_model=Workspace_membersResponse)
async def update_workspace_members(
    id: int,
    data: Workspace_membersUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing workspace_members"""
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )


@router.delete("/batch")
async def delete_workspace_memberss_batch(
    request: Workspace_membersBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple workspace_memberss by their IDs"""
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )


@router.delete("/{id}")
async def delete_workspace_members(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single workspace_members by ID"""
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )