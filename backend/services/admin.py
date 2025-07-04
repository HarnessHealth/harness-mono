"""
Harness - Admin Service
Business logic for admin operations
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text

from backend.api.config import settings
from backend.models.admin import (
    AirflowDAG,
    CostAnomaly,
    CostData,
    DailyCost,
    EvaluationRequest,
    EvaluationRun,
    ModelDeployRequest,
    ModelInfo,
    ModelStatus,
    MonthlyTrend,
    PaperSource,
    PaperStats,
    ServiceCost,
    SystemHealth,
)
from backend.models.database import get_db
from backend.services.cache import cache_service
from backend.services.cost_explorer import CostExplorerService
from backend.utils.s3 import s3_client


class AdminService:
    """Admin service for system management"""

    def __init__(self):
        self.s3_client = s3_client
        self.models_bucket = settings.S3_MODELS_BUCKET
        self.papers_bucket = settings.S3_PAPERS_BUCKET
        self.airflow_url = settings.AIRFLOW_URL
        self.evaluation_runs = {}  # In-memory storage for demo
        self.cost_explorer = None
        self.use_production_costs = settings.AWS_ENVIRONMENT == "production"

        # Initialize Cost Explorer service for production
        if self.use_production_costs:
            try:
                self.cost_explorer = CostExplorerService()
            except Exception as e:
                print(f"Failed to initialize Cost Explorer: {e}")
                self.use_production_costs = False

    # Model Management
    async def list_models(self) -> list[ModelInfo]:
        """List all available models"""
        models = []

        # List models from S3
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.models_bucket, Prefix="models/", Delimiter="/"
            )

            for prefix in response.get("CommonPrefixes", []):
                model_path = prefix["Prefix"]
                model_id = model_path.split("/")[-2]

                # Get model metadata
                metadata = await self._get_model_metadata(model_id)
                if metadata:
                    models.append(metadata)

        except Exception:
            # Fallback to demo data
            models = [
                ModelInfo(
                    id="medgemma-vet-v1",
                    name="MedGemma Veterinary v1",
                    version="1.0.0",
                    status=ModelStatus.DEPLOYED,
                    base_model="google/medgemma-7b",
                    created_at=datetime.utcnow() - timedelta(days=7),
                    updated_at=datetime.utcnow() - timedelta(days=2),
                    training_params={
                        "epochs": 3,
                        "batch_size": 8,
                        "learning_rate": 5e-5,
                        "lora_rank": 16,
                    },
                    performance_metrics={
                        "navle_accuracy": 0.87,
                        "vetqa_f1": 0.82,
                        "clinical_relevance": 0.91,
                    },
                    dataset_info={
                        "total_papers": 15420,
                        "training_samples": 12336,
                        "validation_samples": 3084,
                    },
                    deployed_at=datetime.utcnow() - timedelta(days=2),
                    deployed_by="admin@harness.health",
                ),
                ModelInfo(
                    id="medgemma-vet-v2",
                    name="MedGemma Veterinary v2",
                    version="2.0.0-beta",
                    status=ModelStatus.VALIDATING,
                    base_model="google/medgemma-7b",
                    created_at=datetime.utcnow() - timedelta(days=2),
                    updated_at=datetime.utcnow() - timedelta(hours=6),
                    training_params={
                        "epochs": 5,
                        "batch_size": 16,
                        "learning_rate": 3e-5,
                        "lora_rank": 32,
                    },
                    performance_metrics={
                        "navle_accuracy": 0.89,
                        "vetqa_f1": 0.85,
                        "clinical_relevance": 0.93,
                    },
                    dataset_info={
                        "total_papers": 18750,
                        "training_samples": 15000,
                        "validation_samples": 3750,
                    },
                ),
            ]

        return models

    async def get_model(self, model_id: str) -> ModelInfo | None:
        """Get model details"""
        models = await self.list_models()
        return next((m for m in models if m.id == model_id), None)

    async def deploy_model(self, model_id: str, request: ModelDeployRequest) -> str:
        """Deploy a model"""
        # In production, this would trigger actual deployment
        deployment_id = (
            f"deploy-{model_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        )

        # Update model status
        await cache_service.set(
            f"model_deployment:{model_id}",
            {
                "deployment_id": deployment_id,
                "status": "deploying",
                "request": request.dict(),
                "started_at": datetime.utcnow().isoformat(),
            },
            ttl=3600,
        )

        # Trigger async deployment
        asyncio.create_task(self._deploy_model_async(model_id, deployment_id, request))

        return deployment_id

    async def rollback_model(self, model_id: str) -> str:
        """Rollback model deployment"""
        # In production, this would trigger actual rollback
        return f"Rollback initiated for model {model_id}"

    # Paper Acquisition
    async def get_paper_stats(self) -> PaperStats:
        """Get paper acquisition statistics from S3 bucket"""
        try:
            # Try to get real stats from cache first
            cached_stats = await cache_service.get("paper_stats")
            if cached_stats:
                return PaperStats(**cached_stats)

            # Get real data from S3 bucket
            bucket_name = self.papers_bucket
            papers_by_source = {}
            total_papers = 0
            last_24h_acquired = 0
            last_7d_acquired = 0
            storage_used_gb = 0

            now = datetime.utcnow()
            cutoff_24h = now - timedelta(hours=24)
            cutoff_7d = now - timedelta(days=7)

            # List all metadata files in S3
            response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix="metadata/")

            if "Contents" in response:
                for obj in response["Contents"]:
                    key = obj["Key"]
                    size_mb = obj["Size"] / (1024 * 1024)
                    storage_used_gb += size_mb / 1024

                    # Extract source from path (e.g., metadata/pubmed/file.json)
                    path_parts = key.split("/")
                    if len(path_parts) >= 3:
                        source = path_parts[1]

                        # Get the file and count papers
                        try:
                            file_obj = s3_client.get_object(Bucket=bucket_name, Key=key)
                            content = json.loads(
                                file_obj["Body"].read().decode("utf-8")
                            )

                            if "papers" in content:
                                paper_count = len(content["papers"])
                                total_papers += paper_count
                                papers_by_source[source] = (
                                    papers_by_source.get(source, 0) + paper_count
                                )

                                # Check if crawled in last 24h/7d
                                if "crawled_at" in content:
                                    crawled_time = datetime.fromisoformat(
                                        content["crawled_at"].replace("Z", "+00:00")
                                    )
                                    if crawled_time > cutoff_24h:
                                        last_24h_acquired += paper_count
                                    if crawled_time > cutoff_7d:
                                        last_7d_acquired += paper_count

                        except Exception as e:
                            print(f"Error reading S3 file {key}: {e}")
                            continue

            # Format source names properly
            formatted_sources = {}
            for source, count in papers_by_source.items():
                if source == "pubmed":
                    formatted_sources["PubMed"] = count
                elif source == "europe_pmc":
                    formatted_sources["Europe PMC"] = count
                else:
                    formatted_sources[source.title()] = count

            stats = PaperStats(
                total_papers=total_papers,
                papers_by_source=formatted_sources,
                papers_by_status={
                    "processed": total_papers,
                    "processing": 0,
                    "failed": 0,
                    "pending": 0,
                },
                processing_queue_size=0,
                failed_papers=0,
                last_24h_acquired=last_24h_acquired,
                last_7d_acquired=last_7d_acquired,
                storage_used_gb=round(storage_used_gb, 2),
                embeddings_generated=0,  # Would need to check vector DB
            )

            # Cache the stats for 5 minutes
            await cache_service.set("paper_stats", stats.dict(), expire=300)

            return stats

        except Exception as e:
            print(f"Error getting paper stats from S3: {e}")
            # Fallback to demo data if S3 fails
            return PaperStats(
                total_papers=0,
                papers_by_source={},
                papers_by_status={
                    "processed": 0,
                    "processing": 0,
                    "failed": 0,
                    "pending": 0,
                },
                processing_queue_size=0,
                failed_papers=0,
                last_24h_acquired=0,
                last_7d_acquired=0,
                storage_used_gb=0.0,
                embeddings_generated=0,
            )

    async def get_paper_sources(self) -> list[PaperSource]:
        """Get paper source status from S3 and Lambda function logs"""
        try:
            # Get real data from S3 bucket
            bucket_name = self.papers_bucket
            source_stats = {}

            # List all metadata files in S3
            response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix="metadata/")

            if "Contents" in response:
                for obj in response["Contents"]:
                    key = obj["Key"]
                    last_modified = obj["LastModified"]

                    # Extract source from path (e.g., metadata/pubmed/file.json)
                    path_parts = key.split("/")
                    if len(path_parts) >= 3:
                        source = path_parts[1]

                        if source not in source_stats:
                            source_stats[source] = {
                                "papers_acquired": 0,
                                "last_crawl": last_modified,
                                "last_success": last_modified,
                                "error_count": 0,
                            }

                        # Get the file and count papers
                        try:
                            file_obj = s3_client.get_object(Bucket=bucket_name, Key=key)
                            content = json.loads(
                                file_obj["Body"].read().decode("utf-8")
                            )

                            if "papers" in content:
                                paper_count = len(content["papers"])
                                source_stats[source]["papers_acquired"] += paper_count

                                # Update last crawl time
                                if last_modified > source_stats[source]["last_crawl"]:
                                    source_stats[source]["last_crawl"] = last_modified
                                    source_stats[source]["last_success"] = last_modified

                        except Exception:
                            if source in source_stats:
                                source_stats[source]["error_count"] += 1

            # Build source objects
            sources = []

            # Active sources that we've crawled
            for source_key, stats in source_stats.items():
                if source_key == "pubmed":
                    name = "PubMed"
                    rate_limit_remaining = 950  # With API key
                elif source_key == "europe_pmc":
                    name = "Europe PMC"
                    rate_limit_remaining = None
                else:
                    name = source_key.title()
                    rate_limit_remaining = None

                api_status = "healthy" if stats["error_count"] == 0 else "degraded"
                error_message = (
                    f"{stats['error_count']} crawling errors"
                    if stats["error_count"] > 0
                    else None
                )

                sources.append(
                    PaperSource(
                        name=name,
                        enabled=True,
                        last_crawl=stats["last_crawl"],
                        last_success=(
                            stats["last_success"] if stats["error_count"] == 0 else None
                        ),
                        papers_acquired=stats["papers_acquired"],
                        error_count=stats["error_count"],
                        api_status=api_status,
                        rate_limit_remaining=rate_limit_remaining,
                        error_message=error_message,
                    )
                )

            # Add inactive sources that are configured but not used yet
            active_sources = {s.name for s in sources}
            inactive_sources = [
                ("DOAJ", "Planned - veterinary journal indexing"),
                ("CrossRef", "Planned - DOI-based discovery"),
                ("bioRxiv", "Planned - preprint server"),
                ("arXiv", "Planned - scientific preprints"),
                ("IVIS", "Planned - IVIS veterinary library"),
            ]

            for name, message in inactive_sources:
                if name not in active_sources:
                    sources.append(
                        PaperSource(
                            name=name,
                            enabled=False,
                            last_crawl=None,
                            last_success=None,
                            papers_acquired=0,
                            error_count=0,
                            api_status="down",
                            error_message=message,
                        )
                    )

            return sources

        except Exception as e:
            print(f"Error getting paper sources from S3: {e}")
            # Fallback to minimal config if S3 fails
            return [
                PaperSource(
                    name="PubMed",
                    enabled=True,
                    last_crawl=None,
                    last_success=None,
                    papers_acquired=0,
                    error_count=0,
                    api_status="down",
                    error_message="Unable to fetch source status",
                ),
                PaperSource(
                    name="Europe PMC",
                    enabled=True,
                    last_crawl=None,
                    last_success=None,
                    papers_acquired=0,
                    error_count=0,
                    api_status="down",
                    error_message="Unable to fetch source status",
                ),
            ]

    async def get_processing_queue(
        self, limit: int, status: str | None
    ) -> dict[str, Any]:
        """Get papers in processing queue"""
        # In production, query from database
        queue = {
            "total": 1766,
            "papers": [
                {
                    "id": f"paper-{i}",
                    "title": f"Sample Veterinary Paper {i}",
                    "source": ["PubMed", "Europe PMC", "DOAJ"][i % 3],
                    "status": status or ["processing", "pending", "failed"][i % 3],
                    "added_at": (
                        datetime.utcnow() - timedelta(minutes=i * 5)
                    ).isoformat(),
                    "error": "GROBID processing failed" if i % 3 == 2 else None,
                }
                for i in range(min(limit, 20))
            ],
        }

        return queue

    async def retry_paper_processing(self, paper_id: str) -> str:
        """Retry processing for a failed paper"""
        # In production, trigger actual retry
        return f"Paper {paper_id} queued for retry"

    # Evaluation
    async def list_benchmarks(self) -> list[dict[str, str]]:
        """List available benchmarks"""
        return [
            {
                "id": "navle_sample",
                "name": "NAVLE Sample Questions",
                "description": "North American Veterinary Licensing Exam sample questions",
                "question_count": 29,
            },
            {
                "id": "vetqa_1000",
                "name": "VetQA-1000",
                "description": "Custom veterinary Q&A dataset",
                "question_count": 1000,
            },
            {
                "id": "clinical_cases",
                "name": "Clinical Cases",
                "description": "Real-world clinical case evaluations",
                "question_count": 50,
            },
            {
                "id": "citation_accuracy",
                "name": "Citation Accuracy",
                "description": "Accuracy of literature citations",
                "question_count": 20,
            },
            {
                "id": "safety",
                "name": "Safety Evaluation",
                "description": "Safety and ethics evaluation",
                "question_count": 15,
            },
            {
                "id": "species_specific",
                "name": "Species-Specific",
                "description": "Performance across different species",
                "question_count": 30,
            },
        ]

    async def run_evaluation(self, run_id: str, request: EvaluationRequest):
        """Run evaluation asynchronously"""
        # Store run information
        self.evaluation_runs[run_id] = {
            "status": "running",
            "progress": {},
            "results": {},
        }

        try:
            # Simulate evaluation progress
            for i, benchmark in enumerate(request.benchmarks):
                # Update progress
                progress = (i / len(request.benchmarks)) * 100
                self.evaluation_runs[run_id]["progress"][benchmark] = progress

                # Simulate processing time
                await asyncio.sleep(5)

                # Generate mock results
                self.evaluation_runs[run_id]["results"][benchmark] = {
                    "accuracy": 0.85 + (i * 0.02),
                    "f1_score": 0.83 + (i * 0.02),
                    "precision": 0.84 + (i * 0.01),
                    "recall": 0.82 + (i * 0.03),
                    "latency_p95": 2.5 + (i * 0.1),
                }

            self.evaluation_runs[run_id]["status"] = "completed"

        except Exception as e:
            self.evaluation_runs[run_id]["status"] = "failed"
            self.evaluation_runs[run_id]["error"] = str(e)

    async def get_evaluation_run(self, run_id: str) -> EvaluationRun | None:
        """Get evaluation run details"""
        if run_id not in self.evaluation_runs:
            return None

        run_data = self.evaluation_runs[run_id]

        # Mock run data
        run = EvaluationRun(
            id=run_id,
            model_id="medgemma-vet-v1",
            benchmarks=["navle_sample", "vetqa_1000"],
            status=run_data["status"],
            started_at=datetime.utcnow() - timedelta(minutes=10),
            completed_at=(
                datetime.utcnow() if run_data["status"] == "completed" else None
            ),
            started_by="admin@harness.health",
            results=run_data.get("results"),
            progress=run_data.get("progress", {}),
        )

        return run

    async def stream_evaluation_progress(
        self, run_id: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream evaluation progress events"""
        if run_id not in self.evaluation_runs:
            yield {"error": "Run not found"}
            return

        last_progress = {}

        while True:
            run_data = self.evaluation_runs.get(run_id, {})
            current_progress = run_data.get("progress", {})

            # Send updates only if progress changed
            if current_progress != last_progress:
                yield {
                    "type": "progress",
                    "data": {
                        "run_id": run_id,
                        "status": run_data.get("status"),
                        "progress": current_progress,
                    },
                }
                last_progress = current_progress.copy()

            # Send completion event
            if run_data.get("status") in ["completed", "failed"]:
                yield {
                    "type": "complete",
                    "data": {
                        "run_id": run_id,
                        "status": run_data.get("status"),
                        "results": run_data.get("results"),
                        "error": run_data.get("error"),
                    },
                }
                break

            await asyncio.sleep(1)

    # System Health
    async def get_system_health(self) -> SystemHealth:
        """Get system health status"""
        health = SystemHealth(
            timestamp=datetime.utcnow(),
            services={
                "api": {
                    "status": "healthy",
                    "uptime_seconds": 86400,
                    "version": "1.0.0",
                },
                "worker": {"status": "healthy", "active_tasks": 5, "queue_size": 12},
                "inference": {
                    "status": "healthy",
                    "models_loaded": 2,
                    "avg_latency_ms": 245,
                },
            },
            database_status={"postgresql": True, "redis": True, "weaviate": True},
            cache_status={"connected": True, "memory_used_mb": 234, "hit_rate": 0.89},
            vector_db_status={"connected": True, "documents": 24567, "collections": 3},
            storage_status={
                "s3_connected": True,
                "used_gb": 45.8,
                "available_gb": 954.2,
            },
            gpu_status=[
                {
                    "id": 0,
                    "name": "NVIDIA L4",
                    "memory_used_gb": 12.5,
                    "memory_total_gb": 24.0,
                    "utilization": 67,
                    "temperature": 72,
                }
            ],
            overall_status="healthy",
        )

        # Check actual service health
        try:
            # Check PostgreSQL
            async for session in get_db():
                result = await session.execute(
                    select(func.count()).select_from(text("pg_stat_activity"))
                )
                health.database_status["postgresql"] = result.scalar() > 0
                break
        except:
            health.database_status["postgresql"] = False

        # Update overall status
        if not all(health.database_status.values()):
            health.overall_status = "degraded"

        return health

    async def get_system_metrics(self, period: str) -> dict[str, Any]:
        """Get system performance metrics"""
        # Calculate time range
        period_map = {
            "1h": timedelta(hours=1),
            "6h": timedelta(hours=6),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
        }

        start_time = datetime.utcnow() - period_map[period]

        metrics = {
            "period": period,
            "start_time": start_time.isoformat(),
            "end_time": datetime.utcnow().isoformat(),
            "api": {
                "request_count": 12456,
                "error_rate": 0.02,
                "avg_latency_ms": 145,
                "p95_latency_ms": 287,
                "endpoints": [
                    {"path": "/api/v1/ask", "count": 8234, "avg_ms": 234},
                    {"path": "/api/v1/search", "count": 4222, "avg_ms": 89},
                ],
            },
            "inference": {
                "total_requests": 8234,
                "avg_tokens_per_request": 512,
                "avg_generation_time_ms": 1234,
                "cache_hit_rate": 0.34,
            },
            "resources": {"cpu_usage": [], "memory_usage": [], "gpu_usage": []},
        }

        # Generate time series data
        num_points = {"1h": 12, "6h": 36, "24h": 48, "7d": 84}[period]

        for i in range(num_points):
            timestamp = start_time + (i * period_map[period] / num_points)
            metrics["resources"]["cpu_usage"].append(
                {"timestamp": timestamp.isoformat(), "value": 45 + (i % 10) * 3}
            )
            metrics["resources"]["memory_usage"].append(
                {"timestamp": timestamp.isoformat(), "value": 60 + (i % 8) * 2}
            )
            metrics["resources"]["gpu_usage"].append(
                {"timestamp": timestamp.isoformat(), "value": 55 + (i % 12) * 4}
            )

        return metrics

    async def get_airflow_dags(self) -> list[AirflowDAG]:
        """Get Airflow DAG status"""
        dags = [
            AirflowDAG(
                dag_id="veterinary_corpus_acquisition",
                description="Daily veterinary paper acquisition from multiple sources",
                is_paused=False,
                is_active=True,
                last_parsed_time=datetime.utcnow() - timedelta(hours=1),
                last_run_state="success",
                last_run_start=datetime.utcnow() - timedelta(hours=6),
                next_run=datetime.utcnow() + timedelta(hours=18),
                schedule_interval="0 2 * * *",
                tags=["production", "data-acquisition"],
            ),
            AirflowDAG(
                dag_id="paper_processing_pipeline",
                description="Process PDFs with GROBID and generate embeddings",
                is_paused=False,
                is_active=True,
                last_parsed_time=datetime.utcnow() - timedelta(hours=1),
                last_run_state="running",
                last_run_start=datetime.utcnow() - timedelta(minutes=30),
                schedule_interval="*/30 * * * *",
                tags=["production", "processing"],
            ),
            AirflowDAG(
                dag_id="model_evaluation_daily",
                description="Daily model performance evaluation",
                is_paused=True,
                is_active=True,
                last_parsed_time=datetime.utcnow() - timedelta(hours=2),
                last_run_state="success",
                last_run_start=datetime.utcnow() - timedelta(days=1),
                schedule_interval="0 5 * * *",
                tags=["evaluation", "monitoring"],
            ),
        ]

        return dags

    async def get_airflow_runs(
        self, dag_id: str | None, limit: int
    ) -> list[dict[str, Any]]:
        """Get recent Airflow DAG runs"""
        runs = []

        # Generate mock run data
        for i in range(limit):
            run_time = datetime.utcnow() - timedelta(hours=i * 4)
            runs.append(
                {
                    "dag_id": dag_id or "veterinary_corpus_acquisition",
                    "run_id": f"scheduled__{run_time.strftime('%Y-%m-%dT%H:%M:%S')}",
                    "state": ["success", "success", "failed", "running"][i % 4],
                    "execution_date": run_time.isoformat(),
                    "start_date": run_time.isoformat(),
                    "end_date": (
                        (run_time + timedelta(minutes=45)).isoformat()
                        if i % 4 != 3
                        else None
                    ),
                    "duration": 2700 if i % 4 != 3 else None,
                    "tasks": {
                        "total": 8,
                        "completed": 8 if i % 4 < 2 else (5 if i % 4 == 2 else 3),
                        "failed": 0 if i % 4 < 2 else (3 if i % 4 == 2 else 0),
                    },
                }
            )

        return runs

    # Helper methods
    async def _get_model_metadata(self, model_id: str) -> ModelInfo | None:
        """Get model metadata from S3"""
        try:
            response = self.s3_client.get_object(
                Bucket=self.models_bucket, Key=f"models/{model_id}/metadata.json"
            )
            metadata = json.loads(response["Body"].read())
            return ModelInfo(**metadata)
        except:
            return None

    async def _deploy_model_async(
        self, model_id: str, deployment_id: str, request: ModelDeployRequest
    ):
        """Async model deployment"""
        # Simulate deployment process
        await asyncio.sleep(30)

        # Update deployment status
        await cache_service.set(
            f"model_deployment:{model_id}",
            {
                "deployment_id": deployment_id,
                "status": "deployed",
                "request": request.dict(),
                "completed_at": datetime.utcnow().isoformat(),
            },
            ttl=86400,
        )

    async def get_costs(self, time_range: str) -> CostData:
        """Get AWS cost data"""
        # Use real Cost Explorer in production if available
        if self.use_production_costs and self.cost_explorer:
            try:
                return await self.cost_explorer.get_costs(time_range)
            except Exception as e:
                print(f"Failed to get costs from Cost Explorer: {e}")
                # Fall through to demo data

        # Return demo data for development or if Cost Explorer fails
        # Calculate dates based on time range
        now = datetime.utcnow()
        days = {"7d": 7, "30d": 30, "90d": 90}[time_range]

        # Generate daily costs
        daily_costs = []
        for i in range(days):
            date = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            # Simulate varying daily costs with some randomness
            base_cost = 150 + (i % 7) * 20  # Weekly pattern
            if i % 7 in [5, 6]:  # Lower costs on weekends
                base_cost *= 0.7
            daily_costs.append(
                DailyCost(date=date, total=round(base_cost + (i % 3) * 15, 2))
            )

        # Current month total
        current_month_total = sum(
            dc.total for dc in daily_costs if dc.date.startswith(now.strftime("%Y-%m"))
        )

        # Service breakdown
        service_breakdown = [
            ServiceCost(
                name="EC2",
                description="Compute instances for ECS and training",
                cost=current_month_total * 0.35,
                change=12.5,
            ),
            ServiceCost(
                name="S3",
                description="Storage for papers and models",
                cost=current_month_total * 0.15,
                change=-5.2,
            ),
            ServiceCost(
                name="RDS",
                description="PostgreSQL databases",
                cost=current_month_total * 0.20,
                change=8.3,
            ),
            ServiceCost(
                name="SageMaker",
                description="ML training and endpoints",
                cost=current_month_total * 0.18,
                change=25.7,
            ),
            ServiceCost(
                name="CloudFront",
                description="CDN for web assets",
                cost=current_month_total * 0.05,
                change=2.1,
            ),
            ServiceCost(
                name="Other",
                description="Route53, Lambda, etc.",
                cost=current_month_total * 0.07,
                change=-1.8,
            ),
        ]

        # Monthly trends (last 6 months)
        monthly_trends = []
        for i in range(6):
            month_date = now - timedelta(days=i * 30)
            monthly_trends.append(
                MonthlyTrend(
                    month=month_date.strftime("%B %Y"),
                    compute=2800 + i * 150,
                    storage=1200 + i * 50,
                    database=1500 + i * 80,
                    ml=2200 + i * 200,
                    other=800 + i * 30,
                )
            )

        # Detect anomalies
        anomalies = []
        if days >= 30:
            # Simulate a cost anomaly
            anomalies.append(
                CostAnomaly(
                    service="SageMaker",
                    description="Unusually high training job costs - GPU instance left running",
                    amount=487.50,
                    date=(now - timedelta(days=5)).strftime("%Y-%m-%d"),
                )
            )

        # Calculate projections
        avg_daily = sum(dc.total for dc in daily_costs[:7]) / 7
        days_in_month = 30
        projected_total = avg_daily * days_in_month

        # Budget calculation
        monthly_budget = 5000.0
        budget_utilization = (current_month_total / monthly_budget) * 100

        return CostData(
            current_month={
                "total": round(current_month_total, 2),
                "change": 15.3,  # % change from last month
            },
            today={"total": daily_costs[0].total if daily_costs else 0},
            projected={"total": round(projected_total, 2)},
            budget_utilization=round(budget_utilization, 1),
            monthly_budget=monthly_budget,
            daily_costs=daily_costs[::-1],  # Reverse to show oldest first
            service_breakdown=service_breakdown,
            monthly_trends=monthly_trends[::-1],  # Reverse to show oldest first
            anomalies=anomalies if anomalies else None,
        )
