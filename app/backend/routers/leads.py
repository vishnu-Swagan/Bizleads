import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.leads import LeadsService
from dependencies.auth import get_current_user
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/leads", tags=["leads"])


# ---------- Pydantic Schemas ----------
class LeadsData(BaseModel):
    """Entity data schema (for create/update)"""
    business_name: str
    category: str
    location: str
    country: str
    website_url: Optional[str] = None
    website_score: Optional[int] = None
    social_score: Optional[int] = None
    has_website: Optional[bool] = None
    social_platforms: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    pipeline_stage: Optional[str] = None
    priority: Optional[str] = None
    notes_count: Optional[int] = None
    last_contacted: Optional[str] = None
    data_source: Optional[str] = None
    # JSON-encoded qualification findings and the ISO timestamp of the last
    # qualification pass. Optional[str] (not Optional[str] = None with a bare
    # `str` type) so an explicit null round-trips — see
    # tests/test_save_lead_contract.py for the Pydantic v2 trap this avoids.
    # NULL means never qualified; "[]" means qualified with nothing found.
    findings: Optional[str] = None
    qualified_at: Optional[str] = None


class LeadsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    business_name: Optional[str] = None
    category: Optional[str] = None
    location: Optional[str] = None
    country: Optional[str] = None
    website_url: Optional[str] = None
    website_score: Optional[int] = None
    social_score: Optional[int] = None
    has_website: Optional[bool] = None
    social_platforms: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    pipeline_stage: Optional[str] = None
    priority: Optional[str] = None
    notes_count: Optional[int] = None
    last_contacted: Optional[str] = None
    data_source: Optional[str] = None


class LeadsResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    business_name: str
    category: str
    location: str
    country: str
    website_url: Optional[str] = None
    website_score: Optional[int] = None
    social_score: Optional[int] = None
    has_website: Optional[bool] = None
    social_platforms: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    pipeline_stage: Optional[str] = None
    priority: Optional[str] = None
    notes_count: Optional[int] = None
    last_contacted: Optional[str] = None
    data_source: Optional[str] = None
    findings: Optional[str] = None
    qualified_at: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LeadsListResponse(BaseModel):
    """List response schema"""
    items: List[LeadsResponse]
    total: int
    skip: int
    limit: int


class LeadsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[LeadsData]


class LeadsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: LeadsUpdateData


class LeadsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[LeadsBatchUpdateItem]


class LeadsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=LeadsListResponse)
async def query_leadss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query leadss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying leadss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = LeadsService(db)
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
            user_id=str(current_user.id),
        )
        logger.debug(f"Found {result['total']} leadss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid leads query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying leadss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=LeadsResponse)
async def get_leads(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single leads by ID (user can only see their own records)"""
    logger.debug(f"Fetching leads with id: {id}, fields={fields}")
    
    service = LeadsService(db)
    try:
        result = await service.get_by_id(id, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Leads with id {id} not found")
            raise HTTPException(status_code=404, detail="Leads not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching leads {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=LeadsResponse, status_code=201)
async def create_leads(
    data: LeadsData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new leads"""
    logger.debug(f"Creating new leads with data: {data}")
    
    service = LeadsService(db)
    try:
        result = await service.create(data.model_dump(), user_id=str(current_user.id))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create leads")
        
        logger.info(f"Leads created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating leads: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating leads: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[LeadsResponse], status_code=201)
async def create_leadss_batch(
    request: LeadsBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple leadss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} leadss")
    
    service = LeadsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} leadss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[LeadsResponse])
async def update_leadss_batch(
    request: LeadsBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple leadss in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} leadss")
    
    service = LeadsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} leadss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=LeadsResponse)
async def update_leads(
    id: int,
    data: LeadsUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing leads (requires ownership)"""
    logger.debug(f"Updating leads {id} with data: {data}")

    service = LeadsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Leads with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Leads not found")
        
        logger.info(f"Leads {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating leads {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating leads {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_leadss_batch(
    request: LeadsBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple leadss by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} leadss")
    
    service = LeadsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=str(current_user.id))
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} leadss successfully")
        return {"message": f"Successfully deleted {deleted_count} leadss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_leads(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single leads by ID (requires ownership)"""
    logger.debug(f"Deleting leads with id: {id}")
    
    service = LeadsService(db)
    try:
        success = await service.delete(id, user_id=str(current_user.id))
        if not success:
            logger.warning(f"Leads with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Leads not found")
        
        logger.info(f"Leads {id} deleted successfully")
        return {"message": "Leads deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting leads {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")