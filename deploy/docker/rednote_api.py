"""
RedNote Crawler Web API endpoints
Provides RESTful API for starting, monitoring, and controlling RedNote crawler tasks
"""

import asyncio
import json
from typing import Optional, Dict, List
from uuid import uuid4
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl
from redis import asyncio as aioredis

from crawl4ai.crawlers.rednote.crawler import RedNoteCrawler
from api import handle_task_status, create_task_response, decode_redis_hash
from utils import TaskStatus, get_base_url

# Router for RedNote endpoints
router = APIRouter()

# Dependency placeholders (will be injected from server.py)
_redis = None
_config = None
_token_dep = lambda: None


def init_rednote_router(redis, config, token_dep) -> APIRouter:
    """Initialize RedNote router with dependencies"""
    global _redis, _config, _token_dep
    _redis, _config, _token_dep = redis, config, token_dep
    return router


# ============= Request/Response Models =============

class RedNoteCrawlRequest(BaseModel):
    """Request model for starting a RedNote crawl"""
    search_keyword: str
    max_notes: int = 20
    headless: bool = True
    verbose: bool = False
    # Optional RedNote crawler specific config
    feishu_webhook_url: Optional[str] = None
    storage_dir: Optional[str] = None
    browser_data_dir: Optional[str] = None
    # Minio configuration
    minio_endpoint: Optional[str] = None
    minio_access_key: Optional[str] = None
    minio_secret_key: Optional[str] = None
    minio_bucket: str = "rednote-browser-state"
    minio_secure: bool = True
    minio_region: Optional[str] = None
    minio_profile_name: str = "default"


class RedNoteCrawlJobRequest(BaseModel):
    """Request model for async job-based crawl"""
    search_keyword: str
    max_notes: int = 20
    headless: bool = True
    verbose: bool = False
    feishu_webhook_url: Optional[str] = None
    storage_dir: Optional[str] = None
    browser_data_dir: Optional[str] = None
    minio_endpoint: Optional[str] = None
    minio_access_key: Optional[str] = None
    minio_secret_key: Optional[str] = None
    minio_bucket: str = "rednote-browser-state"
    minio_secure: bool = True
    minio_region: Optional[str] = None
    minio_profile_name: str = "default"


# ============= Helper Functions =============

async def process_rednote_crawl(
    redis: aioredis.Redis,
    task_id: str,
    request: RedNoteCrawlRequest
) -> None:
    """
    Background task to process RedNote crawl
    
    Args:
        redis: Redis connection
        task_id: Task ID
        request: Crawl request parameters
    """
    try:
        # Create RedNote crawler instance
        crawler = RedNoteCrawler(
            feishu_webhook_url=request.feishu_webhook_url,
            storage_dir=request.storage_dir,
            browser_data_dir=request.browser_data_dir,
            minio_endpoint=request.minio_endpoint,
            minio_access_key=request.minio_access_key,
            minio_secret_key=request.minio_secret_key,
            minio_bucket=request.minio_bucket,
            minio_secure=request.minio_secure,
            minio_region=request.minio_region,
            minio_profile_name=request.minio_profile_name
        )
        
        # Update status to processing
        await redis.hset(f"task:{task_id}", mapping={
            "status": TaskStatus.PROCESSING,
            "search_keyword": request.search_keyword,
            "max_notes": str(request.max_notes),
            "started_at": datetime.utcnow().isoformat()
        })
        
        # Run the crawler
        result_json = await crawler.run(
            search_keyword=request.search_keyword,
            max_notes=request.max_notes,
            headless=request.headless,
            verbose=request.verbose
        )
        
        # Parse result
        result_data = json.loads(result_json)
        
        # Update task with result
        await redis.hset(f"task:{task_id}", mapping={
            "status": TaskStatus.COMPLETED,
            "result": result_json,
            "completed_at": datetime.utcnow().isoformat(),
            "total_notes": str(result_data.get('total_notes', 0)),
            "success": str(result_data.get('success', False))
        })
        
    except Exception as e:
        # Update task with error
        await redis.hset(f"task:{task_id}", mapping={
            "status": TaskStatus.FAILED,
            "error": str(e),
            "failed_at": datetime.utcnow().isoformat()
        })


# ============= API Endpoints =============

@router.post("/rednote/crawl")
async def rednote_crawl_sync(
    request: RedNoteCrawlRequest,
    _td: Dict = Depends(lambda: _token_dep())
) -> JSONResponse:
    """
    Synchronously crawl RedNote (blocks until complete)
    
    Returns the crawl result directly
    """
    try:
        crawler = RedNoteCrawler(
            feishu_webhook_url=request.feishu_webhook_url,
            storage_dir=request.storage_dir,
            browser_data_dir=request.browser_data_dir,
            minio_endpoint=request.minio_endpoint,
            minio_access_key=request.minio_access_key,
            minio_secret_key=request.minio_secret_key,
            minio_bucket=request.minio_bucket,
            minio_secure=request.minio_secure,
            minio_region=request.minio_region,
            minio_profile_name=request.minio_profile_name
        )
        
        result_json = await crawler.run(
            search_keyword=request.search_keyword,
            max_notes=request.max_notes,
            headless=request.headless,
            verbose=request.verbose
        )
        
        result_data = json.loads(result_json)
        
        return JSONResponse({
            "success": True,
            "result": result_data,
            "task_id": None  # No task ID for sync requests
        })
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"RedNote crawl failed: {str(e)}"
        )


@router.post("/rednote/job", status_code=202)
async def rednote_crawl_job(
    request: RedNoteCrawlJobRequest,
    background_tasks: BackgroundTasks,
    api_request: Request,
    _td: Dict = Depends(lambda: _token_dep())
) -> JSONResponse:
    """
    Asynchronously crawl RedNote (fire-and-forget)
    
    Returns immediately with a task_id for status polling
    """
    base_url = get_base_url(api_request)
    
    # Generate task ID
    task_id = f"rednote_{uuid4().hex[:8]}"
    
    # Create task in Redis
    await _redis.hset(f"task:{task_id}", mapping={
        "status": TaskStatus.PROCESSING,
        "created_at": datetime.utcnow().isoformat(),
        "search_keyword": request.search_keyword,
        "max_notes": str(request.max_notes),
        "result": "",
        "error": "",
        "type": "rednote_crawl"
    })
    
    # Start background task
    background_tasks.add_task(
        process_rednote_crawl,
        _redis,
        task_id,
        request
    )
    
    return JSONResponse({
        "task_id": task_id,
        "status": TaskStatus.PROCESSING,
        "search_keyword": request.search_keyword,
        "max_notes": request.max_notes,
        "_links": {
            "self": {"href": f"{base_url}/rednote/job/{task_id}"},
            "status": {"href": f"{base_url}/rednote/job/{task_id}"}
        }
    })


@router.get("/rednote/job/{task_id}")
async def rednote_job_status(
    task_id: str,
    api_request: Request,
    keep: bool = False,
    _td: Dict = Depends(lambda: _token_dep())
) -> JSONResponse:
    """
    Get status of a RedNote crawl job
    
    Args:
        task_id: Task ID from /rednote/job endpoint
        keep: Whether to keep the task in Redis after completion
    """
    base_url = get_base_url(api_request)
    
    # Get task from Redis
    task = await _redis.hgetall(f"task:{task_id}")
    if not task:
        raise HTTPException(
            status_code=404,
            detail="Task not found"
        )
    
    task = decode_redis_hash(task)
    
    # Check if it's a RedNote task
    if task.get("type") != "rednote_crawl":
        raise HTTPException(
            status_code=400,
            detail="Task is not a RedNote crawl task"
        )
    
    # Build response
    response = {
        "task_id": task_id,
        "status": task.get("status"),
        "search_keyword": task.get("search_keyword"),
        "max_notes": int(task.get("max_notes", 0)) if task.get("max_notes") else None,
        "created_at": task.get("created_at"),
        "started_at": task.get("started_at"),
        "completed_at": task.get("completed_at"),
        "failed_at": task.get("failed_at"),
        "_links": {
            "self": {"href": f"{base_url}/rednote/job/{task_id}"},
            "status": {"href": f"{base_url}/rednote/job/{task_id}"}
        }
    }
    
    # Add result if completed
    if task.get("status") == TaskStatus.COMPLETED:
        if task.get("result"):
            try:
                response["result"] = json.loads(task.get("result"))
            except:
                response["result"] = task.get("result")
        response["total_notes"] = int(task.get("total_notes", 0)) if task.get("total_notes") else 0
        response["success"] = task.get("success", "false").lower() == "true"
    
    # Add error if failed
    if task.get("status") == TaskStatus.FAILED:
        response["error"] = task.get("error", "Unknown error")
    
    # Cleanup old tasks if requested
    if task.get("status") in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
        if not keep:
            # Keep tasks for 1 hour by default
            from utils import should_cleanup_task
            if should_cleanup_task(task.get("created_at", ""), ttl_seconds=3600):
                await _redis.delete(f"task:{task_id}")
    
    return JSONResponse(response)


@router.delete("/rednote/job/{task_id}")
async def rednote_job_cancel(
    task_id: str,
    _td: Dict = Depends(lambda: _token_dep())
) -> JSONResponse:
    """
    Cancel a RedNote crawl job (if still in progress)
    
    Note: This will mark the task as cancelled, but the background
    process may continue. For true cancellation, you'd need to
    implement process management.
    """
    task = await _redis.hgetall(f"task:{task_id}")
    if not task:
        raise HTTPException(
            status_code=404,
            detail="Task not found"
        )
    
    task = decode_redis_hash(task)
    
    if task.get("status") not in [TaskStatus.PROCESSING]:
        raise HTTPException(
            status_code=400,
            detail=f"Task is {task.get('status')} and cannot be cancelled"
        )
    
    # Mark as cancelled (custom status, or use FAILED)
    await _redis.hset(f"task:{task_id}", mapping={
        "status": TaskStatus.FAILED,
        "error": "Cancelled by user",
        "cancelled_at": datetime.utcnow().isoformat()
    })
    
    return JSONResponse({
        "success": True,
        "message": "Task cancellation requested",
        "task_id": task_id
    })


@router.get("/rednote/jobs")
async def rednote_list_jobs(
    status: Optional[str] = None,
    limit: int = 50,
    _td: Dict = Depends(lambda: _token_dep())
) -> JSONResponse:
    """
    List all RedNote crawl jobs
    
    Args:
        status: Filter by status (processing, completed, failed)
        limit: Maximum number of jobs to return
    """
    # Get all task keys
    keys = await _redis.keys("task:rednote_*")
    
    jobs = []
    for key in keys[:limit]:
        task = await _redis.hgetall(key)
        task = decode_redis_hash(task)
        
        if task.get("type") != "rednote_crawl":
            continue
        
        # Filter by status if specified
        if status and task.get("status") != status:
            continue
        
        job_info = {
            "task_id": key.replace("task:", ""),
            "status": task.get("status"),
            "search_keyword": task.get("search_keyword"),
            "max_notes": int(task.get("max_notes", 0)) if task.get("max_notes") else None,
            "created_at": task.get("created_at"),
            "total_notes": int(task.get("total_notes", 0)) if task.get("total_notes") else None
        }
        jobs.append(job_info)
    
    # Sort by created_at descending
    jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    return JSONResponse({
        "jobs": jobs,
        "total": len(jobs)
    })

