import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.credit_ledger import Credit_ledgerService
from dependencies.auth import get_current_user
from dependencies.tenancy import get_current_workspace
from models.workspaces import Workspaces
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/credit_ledger", tags=["credit_ledger"])


# ---------- Pydantic Schemas ----------
class Credit_ledgerData(BaseModel):
    """Entity data schema (for create/update)"""
    workspace_id: int
    amount: int
    balance_after: int
    action: str
    description: Optional[str] = None
    reference_id: Optional[str] = None
    idempotency_key: Optional[str] = None
class Credit_ledgerUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    workspace_id: Optional[int] = None
    amount: Optional[int] = None
    balance_after: Optional[int] = None
    action: Optional[str] = None
    description: Optional[str] = None
    reference_id: Optional[str] = None
    idempotency_key: Optional[str] = None


class Credit_ledgerResponse(BaseModel):
    """Entity response schema"""
    id: int
    workspace_id: int
    amount: int
    balance_after: int
    action: str
    description: Optional[str] = None
    reference_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Credit_ledgerListResponse(BaseModel):
    """List response schema"""
    items: List[Credit_ledgerResponse]
    total: int
    skip: int
    limit: int


class Credit_ledgerBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Credit_ledgerData]


class Credit_ledgerBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Credit_ledgerUpdateData


class Credit_ledgerBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Credit_ledgerBatchUpdateItem]


class Credit_ledgerBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Credit_ledgerListResponse)
async def query_credit_ledgers(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Credit_ledgerService(db)
    query_dict = {}
    if query:
        try:
            query_dict = json.loads(query)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid query JSON format")
    query_dict["workspace_id"] = workspace.id
    return await service.get_list(skip=skip, limit=limit, query_dict=query_dict, sort=sort)


@router.get("/{id}", response_model=Credit_ledgerResponse)
async def get_credit_ledger(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Credit_ledgerService(db)
    result = await service.get_by_id(id)
    if not result or result.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Not found")
    return result


@router.post("", response_model=Credit_ledgerResponse, status_code=201)
async def create_credit_ledger(
    data: Credit_ledgerData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new credit_ledger"""
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )


@router.post("/batch", response_model=List[Credit_ledgerResponse], status_code=201)
async def create_credit_ledgers_batch(
    request: Credit_ledgerBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple credit_ledgers in a single request"""
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )


@router.put("/batch", response_model=List[Credit_ledgerResponse])
async def update_credit_ledgers_batch(
    request: Credit_ledgerBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple credit_ledgers in a single request"""
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )


@router.put("/{id}", response_model=Credit_ledgerResponse)
async def update_credit_ledger(
    id: int,
    data: Credit_ledgerUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing credit_ledger"""
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )


@router.delete("/batch")
async def delete_credit_ledgers_batch(
    request: Credit_ledgerBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple credit_ledgers by their IDs"""
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )


@router.delete("/{id}")
async def delete_credit_ledger(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single credit_ledger by ID"""
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )