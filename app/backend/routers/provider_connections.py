import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.provider_connections import Provider_connectionsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/provider_connections", tags=["provider_connections"])


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
    """Entity response schema"""
    id: int
    workspace_id: int
    provider_type: str
    provider_name: str
    status: Optional[str] = None
    config_json: Optional[str] = None
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
    db: AsyncSession = Depends(get_db),
):
    """Query provider_connectionss with filtering, sorting, and pagination"""
    logger.debug(f"Querying provider_connectionss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Provider_connectionsService(db)
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
        logger.debug(f"Found {result['total']} provider_connectionss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid provider_connections query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying provider_connectionss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Provider_connectionsResponse)
async def get_provider_connections(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single provider_connections by ID"""
    logger.debug(f"Fetching provider_connections with id: {id}, fields={fields}")
    
    service = Provider_connectionsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Provider_connections with id {id} not found")
            raise HTTPException(status_code=404, detail="Provider_connections not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching provider_connections {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Provider_connectionsResponse, status_code=201)
async def create_provider_connections(
    data: Provider_connectionsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new provider_connections"""
    logger.debug(f"Creating new provider_connections with data: {data}")
    
    service = Provider_connectionsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create provider_connections")
        
        logger.info(f"Provider_connections created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating provider_connections: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating provider_connections: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Provider_connectionsResponse], status_code=201)
async def create_provider_connectionss_batch(
    request: Provider_connectionsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple provider_connectionss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} provider_connectionss")
    
    service = Provider_connectionsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} provider_connectionss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Provider_connectionsResponse])
async def update_provider_connectionss_batch(
    request: Provider_connectionsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple provider_connectionss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} provider_connectionss")
    
    service = Provider_connectionsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} provider_connectionss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Provider_connectionsResponse)
async def update_provider_connections(
    id: int,
    data: Provider_connectionsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing provider_connections"""
    logger.debug(f"Updating provider_connections {id} with data: {data}")

    service = Provider_connectionsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Provider_connections with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Provider_connections not found")
        
        logger.info(f"Provider_connections {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating provider_connections {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating provider_connections {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_provider_connectionss_batch(
    request: Provider_connectionsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple provider_connectionss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} provider_connectionss")
    
    service = Provider_connectionsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} provider_connectionss successfully")
        return {"message": f"Successfully deleted {deleted_count} provider_connectionss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_provider_connections(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single provider_connections by ID"""
    logger.debug(f"Deleting provider_connections with id: {id}")
    
    service = Provider_connectionsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Provider_connections with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Provider_connections not found")
        
        logger.info(f"Provider_connections {id} deleted successfully")
        return {"message": "Provider_connections deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting provider_connections {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")