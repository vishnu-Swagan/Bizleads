import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.credit_ledger import Credit_ledgerService

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
    description: str = None
    reference_id: str = None
    idempotency_key: str = None


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
    db: AsyncSession = Depends(get_db),
):
    """Query credit_ledgers with filtering, sorting, and pagination"""
    logger.debug(f"Querying credit_ledgers: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Credit_ledgerService(db)
    try:
        # Parse query JSON if provided
        query_dict = None
        if query:
            try:
                query_dict = json.loads(query)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid query JSON format")
        
        result = await service.get_list(
            skip=skip, 
            limit=limit,
            query_dict=query_dict,
            sort=sort,
        )
        logger.debug(f"Found {result['total']} credit_ledgers")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid credit_ledger query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying credit_ledgers: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Credit_ledgerResponse)
async def get_credit_ledger(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single credit_ledger by ID"""
    logger.debug(f"Fetching credit_ledger with id: {id}, fields={fields}")
    
    service = Credit_ledgerService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Credit_ledger with id {id} not found")
            raise HTTPException(status_code=404, detail="Credit_ledger not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching credit_ledger {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Credit_ledgerResponse, status_code=201)
async def create_credit_ledger(
    data: Credit_ledgerData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new credit_ledger"""
    logger.debug(f"Creating new credit_ledger with data: {data}")
    
    service = Credit_ledgerService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create credit_ledger")
        
        logger.info(f"Credit_ledger created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating credit_ledger: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating credit_ledger: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Credit_ledgerResponse], status_code=201)
async def create_credit_ledgers_batch(
    request: Credit_ledgerBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple credit_ledgers in a single request"""
    logger.debug(f"Batch creating {len(request.items)} credit_ledgers")
    
    service = Credit_ledgerService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} credit_ledgers successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Credit_ledgerResponse])
async def update_credit_ledgers_batch(
    request: Credit_ledgerBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple credit_ledgers in a single request"""
    logger.debug(f"Batch updating {len(request.items)} credit_ledgers")
    
    service = Credit_ledgerService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} credit_ledgers successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Credit_ledgerResponse)
async def update_credit_ledger(
    id: int,
    data: Credit_ledgerUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing credit_ledger"""
    logger.debug(f"Updating credit_ledger {id} with data: {data}")

    service = Credit_ledgerService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Credit_ledger with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Credit_ledger not found")
        
        logger.info(f"Credit_ledger {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating credit_ledger {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating credit_ledger {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_credit_ledgers_batch(
    request: Credit_ledgerBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple credit_ledgers by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} credit_ledgers")
    
    service = Credit_ledgerService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} credit_ledgers successfully")
        return {"message": f"Successfully deleted {deleted_count} credit_ledgers", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_credit_ledger(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single credit_ledger by ID"""
    logger.debug(f"Deleting credit_ledger with id: {id}")
    
    service = Credit_ledgerService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Credit_ledger with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Credit_ledger not found")
        
        logger.info(f"Credit_ledger {id} deleted successfully")
        return {"message": "Credit_ledger deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting credit_ledger {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")