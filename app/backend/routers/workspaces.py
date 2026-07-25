import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.workspaces import WorkspacesService
from dependencies.auth import get_current_user
from dependencies.tenancy import EntityPolicy, filter_writes
from models.workspaces import Workspaces
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/workspaces", tags=["workspaces"])

WORKSPACES_POLICY = EntityPolicy(
    model=Workspaces,
    scope="user",
    writable=frozenset({"name", "settings_json"}),
)


# ---------- Pydantic Schemas ----------
class WorkspacesData(BaseModel):
    """Entity data schema (for create/update)"""
    name: str
    slug: str
    owner_id: str
    plan: str = None
    trial_ends_at: str = None
    stripe_customer_id: str = None
    stripe_subscription_id: str = None
    subscription_status: str = None
    monthly_credits: int = None
    credits_used: int = None
    credits_reset_at: str = None
    max_seats: int = None
    settings_json: str = None


class WorkspacesUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    name: Optional[str] = None
    slug: Optional[str] = None
    owner_id: Optional[str] = None
    plan: Optional[str] = None
    trial_ends_at: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    subscription_status: Optional[str] = None
    monthly_credits: Optional[int] = None
    credits_used: Optional[int] = None
    credits_reset_at: Optional[str] = None
    max_seats: Optional[int] = None
    settings_json: Optional[str] = None


class WorkspacesResponse(BaseModel):
    """Entity response schema"""
    id: int
    name: str
    slug: str
    owner_id: str
    plan: Optional[str] = None
    trial_ends_at: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    subscription_status: Optional[str] = None
    monthly_credits: Optional[int] = None
    credits_used: Optional[int] = None
    credits_reset_at: Optional[str] = None
    max_seats: Optional[int] = None
    settings_json: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WorkspacesListResponse(BaseModel):
    """List response schema"""
    items: List[WorkspacesResponse]
    total: int
    skip: int
    limit: int


class WorkspacesBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[WorkspacesData]


class WorkspacesBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: WorkspacesUpdateData


class WorkspacesBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[WorkspacesBatchUpdateItem]


class WorkspacesBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=WorkspacesListResponse)
async def query_workspacess(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query workspacess with filtering, sorting, and pagination"""
    logger.debug(f"Querying workspacess: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = WorkspacesService(db)
    try:
        # Parse query JSON if provided
        query_dict = {}
        if query:
            try:
                query_dict = json.loads(query)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid query JSON format")
        query_dict["owner_id"] = current_user.id

        result = await service.get_list(
            skip=skip,
            limit=limit,
            query_dict=query_dict,
            sort=sort,
        )
        logger.debug(f"Found {result['total']} workspacess")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid workspaces query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying workspacess: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=WorkspacesResponse)
async def get_workspaces(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single workspaces by ID"""
    logger.debug(f"Fetching workspaces with id: {id}, fields={fields}")

    service = WorkspacesService(db)
    try:
        result = await service.get_by_id(id)
        if not result or result.owner_id != current_user.id:
            logger.warning(f"Workspaces with id {id} not found")
            raise HTTPException(status_code=404, detail="Workspaces not found")

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching workspaces {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=WorkspacesResponse, status_code=201)
async def create_workspaces(
    data: WorkspacesData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new workspaces"""
    raise HTTPException(
        status_code=403,
        detail="Workspaces are created automatically on first use and cannot be created via this API",
    )


@router.post("/batch", response_model=List[WorkspacesResponse], status_code=201)
async def create_workspacess_batch(
    request: WorkspacesBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple workspacess in a single request"""
    raise HTTPException(status_code=403, detail="Batch operations are not permitted on workspaces")


@router.put("/batch", response_model=List[WorkspacesResponse])
async def update_workspacess_batch(
    request: WorkspacesBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple workspacess in a single request"""
    raise HTTPException(status_code=403, detail="Batch operations are not permitted on workspaces")


@router.put("/{id}", response_model=WorkspacesResponse)
async def update_workspaces(
    id: int,
    data: WorkspacesUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing workspaces"""
    logger.debug(f"Updating workspaces {id} with data: {data}")

    service = WorkspacesService(db)
    existing = await service.get_by_id(id)
    if not existing or existing.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Workspaces not found")

    update_dict = filter_writes(data.model_dump(), WORKSPACES_POLICY, strict=True)
    if not update_dict:
        return existing

    result = await service.update(id, update_dict)
    if not result:
        raise HTTPException(status_code=404, detail="Workspaces not found")

    logger.info(f"Workspaces {id} updated successfully")
    return result


@router.delete("/batch")
async def delete_workspacess_batch(
    request: WorkspacesBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple workspacess by their IDs"""
    raise HTTPException(status_code=403, detail="Batch operations are not permitted on workspaces")


@router.delete("/{id}")
async def delete_workspaces(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single workspaces by ID"""
    raise HTTPException(status_code=403, detail="Workspaces cannot be deleted via this API")