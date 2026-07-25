import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.search_jobs import Search_jobsService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/search_jobs", tags=["search_jobs"])


# ---------- Pydantic Schemas ----------
class Search_jobsData(BaseModel):
    """Entity data schema (for create/update)"""
    workspace_id: int
    status: str = None
    filters_json: str = None
    credits_estimated: int = None
    credits_charged: int = None
    results_count: int = None
    progress_pct: int = None
    error_message: str = None
    started_at: str = None
    completed_at: str = None


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
    db: AsyncSession = Depends(get_db),
):
    """Query search_jobss with filtering, sorting, and pagination"""
    logger.debug(f"Querying search_jobss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Search_jobsService(db)
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
        logger.debug(f"Found {result['total']} search_jobss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid search_jobs query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying search_jobss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Search_jobsResponse)
async def get_search_jobs(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single search_jobs by ID"""
    logger.debug(f"Fetching search_jobs with id: {id}, fields={fields}")
    
    service = Search_jobsService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Search_jobs with id {id} not found")
            raise HTTPException(status_code=404, detail="Search_jobs not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching search_jobs {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Search_jobsResponse, status_code=201)
async def create_search_jobs(
    data: Search_jobsData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new search_jobs"""
    logger.debug(f"Creating new search_jobs with data: {data}")
    
    service = Search_jobsService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create search_jobs")
        
        logger.info(f"Search_jobs created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating search_jobs: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating search_jobs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Search_jobsResponse], status_code=201)
async def create_search_jobss_batch(
    request: Search_jobsBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple search_jobss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} search_jobss")
    
    service = Search_jobsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} search_jobss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Search_jobsResponse])
async def update_search_jobss_batch(
    request: Search_jobsBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple search_jobss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} search_jobss")
    
    service = Search_jobsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} search_jobss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Search_jobsResponse)
async def update_search_jobs(
    id: int,
    data: Search_jobsUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing search_jobs"""
    logger.debug(f"Updating search_jobs {id} with data: {data}")

    service = Search_jobsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Search_jobs with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Search_jobs not found")
        
        logger.info(f"Search_jobs {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating search_jobs {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating search_jobs {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_search_jobss_batch(
    request: Search_jobsBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple search_jobss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} search_jobss")
    
    service = Search_jobsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} search_jobss successfully")
        return {"message": f"Successfully deleted {deleted_count} search_jobss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_search_jobs(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single search_jobs by ID"""
    logger.debug(f"Deleting search_jobs with id: {id}")
    
    service = Search_jobsService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Search_jobs with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Search_jobs not found")
        
        logger.info(f"Search_jobs {id} deleted successfully")
        return {"message": "Search_jobs deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting search_jobs {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")