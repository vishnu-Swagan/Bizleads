import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.lead_notes import Lead_notesService
from dependencies.auth import get_current_user
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/lead_notes", tags=["lead_notes"])


# ---------- Pydantic Schemas ----------
class Lead_notesData(BaseModel):
    """Entity data schema (for create/update)"""
    lead_id: int
    content: str
    note_type: str = None


class Lead_notesUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    lead_id: Optional[int] = None
    content: Optional[str] = None
    note_type: Optional[str] = None


class Lead_notesResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    lead_id: int
    content: str
    note_type: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Lead_notesListResponse(BaseModel):
    """List response schema"""
    items: List[Lead_notesResponse]
    total: int
    skip: int
    limit: int


class Lead_notesBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Lead_notesData]


class Lead_notesBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Lead_notesUpdateData


class Lead_notesBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Lead_notesBatchUpdateItem]


class Lead_notesBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Lead_notesListResponse)
async def query_lead_notess(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query lead_notess with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying lead_notess: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Lead_notesService(db)
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
        logger.debug(f"Found {result['total']} lead_notess")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid lead_notes query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying lead_notess: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Lead_notesResponse)
async def get_lead_notes(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single lead_notes by ID (user can only see their own records)"""
    logger.debug(f"Fetching lead_notes with id: {id}, fields={fields}")
    
    service = Lead_notesService(db)
    try:
        result = await service.get_by_id(id, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Lead_notes with id {id} not found")
            raise HTTPException(status_code=404, detail="Lead_notes not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching lead_notes {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Lead_notesResponse, status_code=201)
async def create_lead_notes(
    data: Lead_notesData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new lead_notes"""
    logger.debug(f"Creating new lead_notes with data: {data}")
    
    service = Lead_notesService(db)
    try:
        result = await service.create(data.model_dump(), user_id=str(current_user.id))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create lead_notes")
        
        logger.info(f"Lead_notes created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating lead_notes: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating lead_notes: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Lead_notesResponse], status_code=201)
async def create_lead_notess_batch(
    request: Lead_notesBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple lead_notess in a single request"""
    logger.debug(f"Batch creating {len(request.items)} lead_notess")
    
    service = Lead_notesService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} lead_notess successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Lead_notesResponse])
async def update_lead_notess_batch(
    request: Lead_notesBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple lead_notess in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} lead_notess")
    
    service = Lead_notesService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} lead_notess successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Lead_notesResponse)
async def update_lead_notes(
    id: int,
    data: Lead_notesUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing lead_notes (requires ownership)"""
    logger.debug(f"Updating lead_notes {id} with data: {data}")

    service = Lead_notesService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Lead_notes with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Lead_notes not found")
        
        logger.info(f"Lead_notes {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating lead_notes {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating lead_notes {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_lead_notess_batch(
    request: Lead_notesBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple lead_notess by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} lead_notess")
    
    service = Lead_notesService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=str(current_user.id))
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} lead_notess successfully")
        return {"message": f"Successfully deleted {deleted_count} lead_notess", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_lead_notes(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single lead_notes by ID (requires ownership)"""
    logger.debug(f"Deleting lead_notes with id: {id}")
    
    service = Lead_notesService(db)
    try:
        success = await service.delete(id, user_id=str(current_user.id))
        if not success:
            logger.warning(f"Lead_notes with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Lead_notes not found")
        
        logger.info(f"Lead_notes {id} deleted successfully")
        return {"message": "Lead_notes deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting lead_notes {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")