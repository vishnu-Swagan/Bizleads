import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.search_jobs import Search_jobsService
from dependencies.auth import get_current_user
from dependencies.tenancy import get_current_workspace
from models.workspaces import Workspaces
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/search_jobs", tags=["search_jobs"])


# ---------- Pydantic Schemas ----------
class Search_jobsData(BaseModel):
    """Entity data schema (for create/update)"""
    workspace_id: int
    status: Optional[str] = None
    filters_json: Optional[str] = None
    credits_estimated: Optional[int] = None
    credits_charged: Optional[int] = None
    results_count: Optional[int] = None
    progress_pct: Optional[int] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
class Search_jobsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    workspace_id: Optional[int] = None
    status: Optional[str] = None
    filters_json: Optional[str] = None
    credits_estimated: Optional[int] = None
    credits_charged: Optional[int] = None
    results_count: Optional[int] = None
    progress_pct: Optional[int] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class Search_jobsResponse(BaseModel):
    """Entity response schema"""
    id: int
    workspace_id: int
    status: Optional[str] = None
    filters_json: Optional[str] = None
    credits_estimated: Optional[int] = None
    credits_charged: Optional[int] = None
    results_count: Optional[int] = None
    progress_pct: Optional[int] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Search_jobsListResponse(BaseModel):
    """List response schema"""
    items: List[Search_jobsResponse]
    total: int
    skip: int
    limit: int


class Search_jobsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Search_jobsData]


class Search_jobsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Search_jobsUpdateData


class Search_jobsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Search_jobsBatchUpdateItem]


class Search_jobsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Search_jobsListResponse)
async def query_search_jobss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Search_jobsService(db)
    query_dict = {}
    if query:
        try:
            query_dict = json.loads(query)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid query JSON format")
    query_dict["workspace_id"] = workspace.id
    return await service.get_list(skip=skip, limit=limit, query_dict=query_dict, sort=sort)


@router.get("/{id}", response_model=Search_jobsResponse)
async def get_search_jobs(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Search_jobsService(db)
    result = await service.get_by_id(id)
    if not result or result.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Not found")
    return result


@router.post("", response_model=Search_jobsResponse, status_code=201)
async def create_search_jobs(
    data: Search_jobsData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new search_jobs"""
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )


@router.post("/batch", response_model=List[Search_jobsResponse], status_code=201)
async def create_search_jobss_batch(
    request: Search_jobsBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple search_jobss in a single request"""
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )


@router.put("/batch", response_model=List[Search_jobsResponse])
async def update_search_jobss_batch(
    request: Search_jobsBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple search_jobss in a single request"""
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )


@router.put("/{id}", response_model=Search_jobsResponse)
async def update_search_jobs(
    id: int,
    data: Search_jobsUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing search_jobs"""
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )


@router.delete("/batch")
async def delete_search_jobss_batch(
    request: Search_jobsBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple search_jobss by their IDs"""
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )


@router.delete("/{id}")
async def delete_search_jobs(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single search_jobs by ID"""
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )