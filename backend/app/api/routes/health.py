"""
Health check endpoints — useful for load balancers, k8s liveness/readiness
probes, and manual debugging.
"""
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.database import check_db_connection, check_db_connection_verbose
from app.core.kafka import check_kafka_connection_verbose
from app.core.redis import check_redis_connection_verbose

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health() -> dict:
    """Liveness probe — is the process up? No DB dependency, always fast."""
    return {"status": "ok"}


@router.get("/db")
def health_db() -> JSONResponse:
    """Readiness probe — can we actually reach Postgres right now?"""
    result = check_db_connection_verbose()
    ok = result.get("status") == "ok"
    return JSONResponse(
        content=result,
        status_code=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@router.get("/redis")
def health_redis() -> JSONResponse:
    """Readiness probe — can we actually reach Redis right now?"""
    result = check_redis_connection_verbose()
    ok = result.get("status") == "ok"
    return JSONResponse(
        content=result,
        status_code=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@router.get("/kafka")
def health_kafka() -> JSONResponse:
    """Readiness probe — can we actually reach the Kafka broker right now?"""
    result = check_kafka_connection_verbose()
    ok = result.get("status") == "ok"
    return JSONResponse(
        content=result,
        status_code=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@router.get("/ready")
def readiness() -> JSONResponse:
    """Simple boolean readiness check for orchestrators that just need 200/503."""
    ok = check_db_connection()
    return JSONResponse(
        content={"ready": ok},
        status_code=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE,
    )