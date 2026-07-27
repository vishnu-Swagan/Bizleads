import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from dependencies.tenancy import get_current_workspace
from models.workspaces import Workspaces
from schemas.auth import UserResponse
from services.offer_profiles import Offer_profilesService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/offer_profiles", tags=["offer_profiles"])


# ---------- Pydantic Schemas ----------
class Offer_profilesData(BaseModel):
    """Entity data schema (for create/update)"""
    workspace_id: int
    services: Optional[str] = None
    platforms: Optional[str] = None
    price_range_min: Optional[int] = None
    price_range_max: Optional[int] = None
    target_categories: Optional[str] = None
    target_geographies: Optional[str] = None
    languages: Optional[str] = None
    min_client_size: Optional[str] = None
    max_client_size: Optional[str] = None
    monthly_capacity: Optional[int] = None
    preferred_channels: Optional[str] = None
    portfolio_tags: Optional[str] = None
class Offer_profilesUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    workspace_id: Optional[int] = None
    services: Optional[str] = None
    platforms: Optional[str] = None
    price_range_min: Optional[int] = None
    price_range_max: Optional[int] = None
    target_categories: Optional[str] = None
    target_geographies: Optional[str] = None
    languages: Optional[str] = None
    min_client_size: Optional[str] = None
    max_client_size: Optional[str] = None
    monthly_capacity: Optional[int] = None
    preferred_channels: Optional[str] = None
    portfolio_tags: Optional[str] = None


class Offer_profilesResponse(BaseModel):
    """Entity response schema"""
    id: int
    workspace_id: int
    services: Optional[str] = None
    platforms: Optional[str] = None
    price_range_min: Optional[int] = None
    price_range_max: Optional[int] = None
    target_categories: Optional[str] = None
    target_geographies: Optional[str] = None
    languages: Optional[str] = None
    min_client_size: Optional[str] = None
    max_client_size: Optional[str] = None
    monthly_capacity: Optional[int] = None
    preferred_channels: Optional[str] = None
    portfolio_tags: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Offer_profilesListResponse(BaseModel):
    """List response schema"""
    items: List[Offer_profilesResponse]
    total: int
    skip: int
    limit: int


class Offer_profilesBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Offer_profilesData]


class Offer_profilesBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Offer_profilesUpdateData


class Offer_profilesBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Offer_profilesBatchUpdateItem]


class Offer_profilesBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Offer_profilesListResponse)
async def query_offer_profiless(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Offer_profilesService(db)
    query_dict = {}
    if query:
        try:
            query_dict = json.loads(query)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid query JSON format")
    query_dict["workspace_id"] = workspace.id
    return await service.get_list(skip=skip, limit=limit, query_dict=query_dict, sort=sort)


@router.get("/{id}", response_model=Offer_profilesResponse)
async def get_offer_profiles(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Offer_profilesService(db)
    result = await service.get_by_id(id)
    if not result or result.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Not found")
    return result


@router.post("", response_model=Offer_profilesResponse, status_code=201)
async def create_offer_profiles(
    data: Offer_profilesData,
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Offer_profilesService(db)
    payload = data.model_dump()
    payload["workspace_id"] = workspace.id
    result = await service.create(payload)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to create offer profile")
    return result


@router.post("/batch", response_model=List[Offer_profilesResponse], status_code=201)
async def create_offer_profiless_batch(
    request: Offer_profilesBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=403, detail="Batch operations are not permitted on offer profiles")


@router.put("/batch", response_model=List[Offer_profilesResponse])
async def update_offer_profiless_batch(
    request: Offer_profilesBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=403, detail="Batch operations are not permitted on offer profiles")


@router.put("/{id}", response_model=Offer_profilesResponse)
async def update_offer_profiles(
    id: int,
    data: Offer_profilesUpdateData,
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Offer_profilesService(db)
    existing = await service.get_by_id(id)
    if not existing or existing.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Not found")

    update_dict = {k: v for k, v in data.model_dump().items() if v is not None and k != "workspace_id"}
    if not update_dict:
        return existing
    return await service.update(id, update_dict)


@router.delete("/batch")
async def delete_offer_profiless_batch(
    request: Offer_profilesBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=403, detail="Batch operations are not permitted on offer profiles")


@router.delete("/{id}")
async def delete_offer_profiles(
    id: int,
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Offer_profilesService(db)
    existing = await service.get_by_id(id)
    if not existing or existing.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Not found")
    await service.delete(id)
    return {"message": "Offer profile deleted", "id": id}
