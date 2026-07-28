from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.application.service import ChallengeService
from app.api import schemas
from app.persistence.repositories import StaleVersionError

router = APIRouter(tags=["challenge"])



def get_service(request: Request) -> ChallengeService:
    return request.app.state.service


@router.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"status": "ok", "message": "magicpin Vera AI Challenge bot"}


@router.get("/healthz", response_model=schemas.HealthResponse)
def healthz(service: ChallengeService = Depends(get_service)) -> schemas.HealthResponse:
    return service.health()


@router.get("/metadata", response_model=schemas.MetadataResponse)
def metadata(service: ChallengeService = Depends(get_service)) -> schemas.MetadataResponse:
    return service.metadata()


@router.post("/context", response_model=schemas.ContextAckResponse)
def context(request: schemas.ContextRequest, service: ChallengeService = Depends(get_service)) -> schemas.ContextAckResponse:
    try:
        return service.ingest_context(request)
    except StaleVersionError as error:
        return JSONResponse(
            status_code=409,
            content={"accepted": False, "reason": "stale_version", "current_version": error.current_version},
        )


@router.post("/tick", response_model=schemas.TickResponse)
def tick(request: schemas.TickRequest, service: ChallengeService = Depends(get_service)) -> schemas.TickResponse:
    return service.tick(request)


@router.post("/reply", response_model=schemas.ReplyResponse)
def reply(request: schemas.ReplyRequest, service: ChallengeService = Depends(get_service)) -> schemas.ReplyResponse:
    return service.reply(request)
