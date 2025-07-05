"""
Harness - Admin API Router
Provides admin endpoints for model management, paper statistics, and evaluation
"""

import asyncio
import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from backend.api.middleware.admin_auth import admin_auth, security
from backend.models.admin import (
    AirflowDAG,
    CostData,
    EvaluationRequest,
    EvaluationRun,
    ModelDeployRequest,
    ModelInfo,
    PaperSource,
    PaperStats,
    SystemHealth,
)
from backend.models.user import UserRole
from backend.services.admin import AdminService

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
admin_service = AdminService()


# Model Management Endpoints
@router.get("/models", response_model=list[ModelInfo])
async def list_models(
    request: Request, credentials=Depends(security)
) -> list[ModelInfo]:
    """List all available models with their status"""
    user = await admin_auth.get_current_user(request, credentials)
    return await admin_service.list_models()


@router.get("/models/{model_id}", response_model=ModelInfo)
async def get_model_details(
    model_id: str, request: Request, credentials=Depends(security)
) -> ModelInfo:
    """Get detailed information about a specific model"""
    user = await admin_auth.get_current_user(request, credentials)
    model = await admin_service.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@router.post("/models/{model_id}/deploy")
async def deploy_model(
    model_id: str,
    deploy_request: ModelDeployRequest,
    request: Request,
    credentials=Depends(security),
) -> dict[str, str]:
    """Deploy a model to production"""
    user = await admin_auth.get_current_user(request, credentials)

    # Require admin role for deployment
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await admin_service.deploy_model(model_id, deploy_request)
    return {"status": "success", "deployment_id": result}


@router.post("/models/{model_id}/rollback")
async def rollback_model(
    model_id: str, request: Request, credentials=Depends(security)
) -> dict[str, str]:
    """Rollback a model deployment"""
    user = await admin_auth.get_current_user(request, credentials)

    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await admin_service.rollback_model(model_id)
    return {"status": "success", "message": result}


# Paper Acquisition Endpoints
@router.get("/papers/stats", response_model=PaperStats)
async def get_paper_statistics(
    request: Request, credentials=Depends(security)
) -> PaperStats:
    """Get paper acquisition statistics"""
    user = await admin_auth.get_current_user(request, credentials)
    return await admin_service.get_paper_stats()


@router.get("/papers/sources", response_model=list[PaperSource])
async def get_paper_sources(
    request: Request, credentials=Depends(security)
) -> list[PaperSource]:
    """Get status of all paper sources"""
    user = await admin_auth.get_current_user(request, credentials)
    return await admin_service.get_paper_sources()


@router.get("/papers/processing-queue")
async def get_processing_queue(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    status: str | None = None,
    credentials=Depends(security),
) -> dict[str, Any]:
    """Get papers in processing queue"""
    user = await admin_auth.get_current_user(request, credentials)
    return await admin_service.get_processing_queue(limit, status)


@router.post("/papers/retry/{paper_id}")
async def retry_paper_processing(
    paper_id: str, request: Request, credentials=Depends(security)
) -> dict[str, str]:
    """Retry processing for a failed paper"""
    user = await admin_auth.get_current_user(request, credentials)

    if user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403, detail="Write access required")

    result = await admin_service.retry_paper_processing(paper_id)
    return {"status": "success", "message": result}


# Evaluation Endpoints
@router.get("/evaluation/benchmarks")
async def list_benchmarks(
    request: Request, credentials=Depends(security)
) -> list[dict[str, str]]:
    """List available evaluation benchmarks"""
    user = await admin_auth.get_current_user(request, credentials)
    return await admin_service.list_benchmarks()


@router.post("/evaluation/run", response_model=EvaluationRun)
async def start_evaluation(
    eval_request: EvaluationRequest, request: Request, credentials=Depends(security)
) -> EvaluationRun:
    """Start a new evaluation run"""
    user = await admin_auth.get_current_user(request, credentials)

    if user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403, detail="Write access required")

    # Create evaluation run
    run_id = str(uuid4())
    run = EvaluationRun(
        id=run_id,
        model_id=eval_request.model_id,
        benchmarks=eval_request.benchmarks,
        status="running",
        started_at=datetime.utcnow(),
        started_by=user.email,
    )

    # Start evaluation in background
    asyncio.create_task(admin_service.run_evaluation(run_id, eval_request))

    return run


@router.get("/evaluation/runs/{run_id}", response_model=EvaluationRun)
async def get_evaluation_run(
    run_id: str, request: Request, credentials=Depends(security)
) -> EvaluationRun:
    """Get evaluation run details"""
    user = await admin_auth.get_current_user(request, credentials)
    run = await admin_service.get_evaluation_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return run


@router.get("/evaluation/runs/{run_id}/stream")
async def stream_evaluation_progress(
    run_id: str, request: Request, credentials=Depends(security)
):
    """Stream evaluation progress using Server-Sent Events"""
    user = await admin_auth.get_current_user(request, credentials)

    async def event_generator():
        """Generate SSE events"""
        async for event in admin_service.stream_evaluation_progress(run_id):
            yield f"data: {json.dumps(event)}\n\n"

            # Check if client disconnected
            if await request.is_disconnected():
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# System Health Endpoints
@router.get("/health/services", response_model=SystemHealth)
async def get_system_health(
    request: Request, credentials=Depends(security)
) -> SystemHealth:
    """Get health status of all services"""
    user = await admin_auth.get_current_user(request, credentials)
    return await admin_service.get_system_health()


@router.get("/health/metrics")
async def get_system_metrics(
    request: Request,
    period: str = Query("1h", regex="^(1h|6h|24h|7d)$"),
    credentials=Depends(security),
) -> dict[str, Any]:
    """Get system performance metrics"""
    user = await admin_auth.get_current_user(request, credentials)
    return await admin_service.get_system_metrics(period)


@router.get("/airflow/dags", response_model=list[AirflowDAG])
async def get_airflow_dags(
    request: Request, credentials=Depends(security)
) -> list[AirflowDAG]:
    """Get Airflow DAG status"""
    user = await admin_auth.get_current_user(request, credentials)
    return await admin_service.get_airflow_dags()


@router.get("/airflow/runs")
async def get_airflow_runs(
    request: Request,
    dag_id: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    credentials=Depends(security),
) -> list[dict[str, Any]]:
    """Get recent Airflow DAG runs"""
    user = await admin_auth.get_current_user(request, credentials)
    return await admin_service.get_airflow_runs(dag_id, limit)


# Costs Endpoints
@router.get("/costs", response_model=CostData)
async def get_costs(
    request: Request,
    time_range: str = Query("30d", regex="^(7d|30d|90d)$"),
    credentials=Depends(security),
) -> CostData:
    """Get AWS cost data for the specified time range"""
    user = await admin_auth.get_current_user(request, credentials)
    return await admin_service.get_costs(time_range)
