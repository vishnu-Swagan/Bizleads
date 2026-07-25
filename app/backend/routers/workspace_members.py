import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.workspace_members import Workspace_membersService

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/workspace_members", tags=["workspace_members"])


# ---------- Pydantic Schemas ----------
class Workspace_membersData(BaseModel):
    """Entity data schema (for create/update)"""
    workspace_id: int
    role: str = None
    invited_email: str = None
    status: str = None


class Workspace_membersUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    workspace_id: Optional[int] = None
    role: Optional[str] = None
    invited_email: Optional[str] = None
    status: Optional[str] = None


class Workspace_membersResponse(BaseModel):
    """Entity response schema"""
    id: int
    workspace_id: int
    role: Optional[str] = None
    invited_email: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Workspace_membersListResponse(BaseModel):
    """List response schema"""
    items: List[Workspace_membersResponse]
    total: int
    skip: int
    limit: int


class Workspace_membersBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Workspace_membersData]


class Workspace_membersBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Workspace_membersUpdateData


class Workspace_membersBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Workspace_membersBatchUpdateItem]


class Workspace_membersBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Workspace_membersListResponse)
async def query_workspace_memberss(
    query: str = Query(None, description='Query conditions as JSON, e.g. {"id":2} or {"id":{"$gte":2}}'),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Query workspace_memberss with filtering, sorting, and pagination"""
    logger.debug(f"Querying workspace_memberss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Workspace_membersService(db)
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
        logger.debug(f"Found {result['total']} workspace_memberss")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid workspace_members query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error querying workspace_memberss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Workspace_membersResponse)
async def get_workspace_members(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get a single workspace_members by ID"""
    logger.debug(f"Fetching workspace_members with id: {id}, fields={fields}")
    
    service = Workspace_membersService(db)
    try:
        result = await service.get_by_id(id)
        if not result:
            logger.warning(f"Workspace_members with id {id} not found")
            raise HTTPException(status_code=404, detail="Workspace_members not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching workspace_members {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Workspace_membersResponse, status_code=201)
async def create_workspace_members(
    data: Workspace_membersData,
    db: AsyncSession = Depends(get_db),
):
    """Create a new workspace_members"""
    logger.debug(f"Creating new workspace_members with data: {data}")
    
    service = Workspace_membersService(db)
    try:
        result = await service.create(data.model_dump())
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create workspace_members")
        
        logger.info(f"Workspace_members created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating workspace_members: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating workspace_members: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Workspace_membersResponse], status_code=201)
async def create_workspace_memberss_batch(
    request: Workspace_membersBatchCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create multiple workspace_memberss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} workspace_memberss")
    
    service = Workspace_membersService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump())
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} workspace_memberss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Workspace_membersResponse])
async def update_workspace_memberss_batch(
    request: Workspace_membersBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update multiple workspace_memberss in a single request"""
    logger.debug(f"Batch updating {len(request.items)} workspace_memberss")
    
    service = Workspace_membersService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} workspace_memberss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Workspace_membersResponse)
async def update_workspace_members(
    id: int,
    data: Workspace_membersUpdateData,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing workspace_members"""
    logger.debug(f"Updating workspace_members {id} with data: {data}")

    service = Workspace_membersService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict)
        if not result:
            logger.warning(f"Workspace_members with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Workspace_members not found")
        
        logger.info(f"Workspace_members {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating workspace_members {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating workspace_members {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_workspace_memberss_batch(
    request: Workspace_membersBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple workspace_memberss by their IDs"""
    logger.debug(f"Batch deleting {len(request.ids)} workspace_memberss")
    
    service = Workspace_membersService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} workspace_memberss successfully")
        return {"message": f"Successfully deleted {deleted_count} workspace_memberss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_workspace_members(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single workspace_members by ID"""
    logger.debug(f"Deleting workspace_members with id: {id}")
    
    service = Workspace_membersService(db)
    try:
        success = await service.delete(id)
        if not success:
            logger.warning(f"Workspace_members with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Workspace_members not found")
        
        logger.info(f"Workspace_members {id} deleted successfully")
        return {"message": "Workspace_members deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting workspace_members {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")