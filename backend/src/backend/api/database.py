"""Database readiness and opt-in development metadata endpoints."""

from fastapi import APIRouter, HTTPException, Request, Response

from backend.database.errors import DatabaseAccessError
from backend.database.models import DatabaseInspection, DatabaseReadiness
from backend.database.service import DatabaseService

router = APIRouter()


def service(request: Request) -> DatabaseService:
    return request.app.state.database_service


@router.get("/ready", response_model=DatabaseReadiness, tags=["readiness"])
def readiness(request: Request, response: Response) -> DatabaseReadiness:
    result = service(request).readiness()
    if result.status == "not_ready":
        response.status_code = 503
    return result


@router.get("/dev/database", response_model=DatabaseInspection, tags=["development"])
def database_metadata(request: Request) -> DatabaseInspection:
    if (
        request.app.state.settings.production
        or not request.app.state.settings.database_metadata_enabled
    ):
        raise HTTPException(status_code=404, detail="Not Found")
    try:
        return service(request).inspect()
    except DatabaseAccessError as error:
        raise HTTPException(status_code=503, detail={"reason": error.code}) from error
