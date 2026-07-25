import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.offer_profiles import Offer_profilesService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/offer_profiles", tags=["offer_profiles"])


# ---------- Pydantic Schemas ----------
class Offer_profilesData(BaseModel):
    """Entity data schema (for create/update)"""
    workspace_id: int
    services: str = None
    platforms: str = None
    price_range_min: int = None
    price_range_max: int = None
    target_categories: str = None
    target_geographies: str = None
    languages: str = None
    min_client_size: str = None
    max_client_size: str = None
    monthly_capacity: int = None
    preferred_channels: str = None
    portfolio_tags: str = None


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
    db: AsyncSession = Depends(get_db),
):
    """Query offer_profiless with filtering, sorting, and pagination"""
    logger.debug(f"Querying offer_profiless: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Offer_profilesService(db)
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
        logger.debug(f"Found {result['total']} offer_profiless")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid offer_profiles query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying offer_profiless: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Offer_profilesResponse)
async def get_offer_profiles(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single offer_profiles by ID"""
    logger.debug(f"Fetching offer_profiles with id: {id}, fields={fields}")
    
    service = Offer_profilesService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Offer_profiles with id {id} not found")
            raise HTTPException(status_code=404, detail="Offer_profiles not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching offer_profiles {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Offer_profilesResponse, status_code=201)
async def create_offer_profiles(
    data: Offer_profilesData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new offer_profiles"""
    logger.debug(f"Creating new offer_profiles with data: {data}")
    
    service = Offer_profilesService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create offer_profiles")
        
        logger.info(f"Offer_profiles created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating offer_profiles: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating offer_profiles: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Offer_profilesResponse], status_code=201)
async def create_offer_profiless_batch(
    request: Offer_profilesBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple offer_profiless in a single request"""
    logger.debug(f"Batch creating {len(request.items)} offer_profiless")
    
    service = Offer_profilesService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} offer_profiless successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Offer_profilesResponse])
async def update_offer_profiless_batch(
    request: Offer_profilesBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple offer_profiless in a single request"""
    logger.debug(f"Batch updating {len(request.items)} offer_profiless")
    
    service = Offer_profilesService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} offer_profiless successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Offer_profilesResponse)
async def update_offer_profiles(
    id: int,
    data: Offer_profilesUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing offer_profiles"""
    logger.debug(f"Updating offer_profiles {id} with data: {data}")

    service = Offer_profilesService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Offer_profiles with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Offer_profiles not found")
        
        logger.info(f"Offer_profiles {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating offer_profiles {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating offer_profiles {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_offer_profiless_batch(
    request: Offer_profilesBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple offer_profiless by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} offer_profiless")
    
    service = Offer_profilesService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} offer_profiless successfully")
        return {"message": f"Successfully deleted {deleted_count} offer_profiless", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_offer_profiles(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single offer_profiles by ID"""
    logger.debug(f"Deleting offer_profiles with id: {id}")
    
    service = Offer_profilesService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Offer_profiles with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Offer_profiles not found")
        
        logger.info(f"Offer_profiles {id} deleted successfully")
        return {"message": "Offer_profiles deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting offer_profiles {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")