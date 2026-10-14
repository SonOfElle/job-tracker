"""Job Application Tracker API."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import Depends, FastAPI, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select, text
from sqlmodel import Session

from app.database import check_schema, get_session
from app.models import (
    Application,
    ApplicationCreate,
    ApplicationRead,
    ApplicationStatus,
    ApplicationUpdate,
    StrategyType,
)

from app.source_parser import derive_source
from app.storage import (
    cv_full_path,
    delete_cv_file,
    sanitize_filename,
    save_cv,
)

logger = logging.getLogger("job_tracker")
logging.basicConfig(level=logging.INFO)
logging.getLogger("alembic").setLevel(logging.WARNING)
# Days until auto-scheduled follow-up, per status. None = no follow-up.
FOLLOW_UP_DAYS: dict[str, int | None] = {
    "Applied": None,
    "Screening": 5,
    "Technical": 5,
    "Offer": 3,
    "Rejected": None,
}

@asynccontextmanager
async def lifespan(_: FastAPI):
    check_schema()
    logger.info("Database schema verified.")
    yield


app = FastAPI(
    title="Job Application Tracker API",
    version="0.1.0",
    lifespan=lifespan,
)


def _get_or_404(session: Session, application_id: int) -> Application:
    application = session.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found")
    return application


# ---- Ops ---------------------------------------------------------------- #

@app.get("/health", tags=["ops"])
def health(session: Session = Depends(get_session)) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc}") from exc
    return {"status": "ok"}


@app.get("/", tags=["ops"])
def root() -> dict[str, str]:
    return {"service": "job-application-tracker", "docs": "/docs"}


# ---- CRUD --------------------------------------------------------------- #

@app.post("/applications", response_model=ApplicationRead, status_code=201, tags=["applications"])
def create_application(
    payload: ApplicationCreate,
    session: Session = Depends(get_session),
) -> Application:
    application = Application.model_validate(payload)
    if application.source is None:
        application.source = derive_source(application.job_link)
    session.add(application)
    session.commit()
    session.refresh(application)
    return application

@app.get("/applications/{application_id}", response_model=ApplicationRead, tags=["applications"])
def get_application(application_id: int, session: Session = Depends(get_session)) -> Application:
    return _get_or_404(session, application_id)


@app.get("/applications", response_model=List[ApplicationRead], tags=["applications"])
def list_applications(
    session: Session = Depends(get_session),
    status_filter: Optional[ApplicationStatus] = Query(None, alias="status"),
    strategy_type: Optional[StrategyType] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[ApplicationRead]:
    stmt = select(Application)
    if status_filter is not None:
        stmt = stmt.where(Application.status == status_filter.value)
    if strategy_type is not None:
        stmt = stmt.where(Application.strategy_type == strategy_type.value)
    stmt = stmt.order_by(Application.date_applied.desc()).offset(offset).limit(limit)

    rows = session.execute(stmt).all()

    results: List[ApplicationRead] = []
    for row in rows:
        # SQLAlchemy Row objects wrap the entity; unwrap explicitly.
        obj = row[0] if not isinstance(row, Application) else row
        results.append(ApplicationRead.model_validate(obj, from_attributes=True))
    return results

@app.patch("/applications/{application_id}", response_model=ApplicationRead, tags=["applications"])
def update_application(
    application_id: int,
    payload: ApplicationUpdate,
    session: Session = Depends(get_session),
) -> Application:
    application = _get_or_404(session, application_id)
    updates = payload.model_dump(exclude_unset=True)

    # Auto-stamp timestamps on status transitions (user never types these).
    if "status" in updates and updates["status"] != application.status:
        now = datetime.now(timezone.utc)
        new_status = updates["status"]

        if new_status in ("Screening", "Technical", "Offer") and application.first_response_at is None:
            application.first_response_at = now
        if new_status == "Technical" and application.first_interview_at is None:
            application.first_interview_at = now
        if new_status == "Offer" and application.offer_at is None:
            application.offer_at = now
        if new_status == "Rejected" and application.rejected_at is None:
            application.rejected_at = now

        # Auto follow-up: only when the user didn't explicitly set one.
        if "next_follow_up" not in updates:
            days = FOLLOW_UP_DAYS.get(new_status)
            application.next_follow_up = (
                (now + timedelta(days=days)).date() if days is not None else None
            )

    # If the link is being updated and the user didn't set source in the same
    # request, re-derive source from the new link. Cleared links leave source alone.
    if "job_link" in updates and "source" not in updates:
        new_link = updates["job_link"]
        if new_link:
            updates["source"] = derive_source(new_link)
            
    application.sqlmodel_update(updates)
    session.add(application)
    session.commit()
    session.refresh(application)
    return application

@app.delete("/applications/{application_id}", status_code=204, tags=["applications"])
def delete_application(application_id: int, session: Session = Depends(get_session)) -> Response:
    application = _get_or_404(session, application_id)
    session.delete(application)
    session.commit()
    return Response(status_code=204)

# ---- CV ---------------------------------------------------------------- #

@app.post("/applications/{application_id}/cv", response_model=ApplicationRead, tags=["applications"])
def upload_cv(
    application_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> Application:
    application = _get_or_404(session, application_id)
    filename = sanitize_filename(file.filename or "cv.pdf")

    try:
        rel_path, size = save_cv(application_id, filename, file.file)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    old_path = application.cv_path
    application.cv_path = rel_path
    application.cv_filename = filename
    session.add(application)
    session.commit()
    session.refresh(application)

    # If the previous CV had a different filename, remove the old file.
    if old_path and old_path != rel_path:
        delete_cv_file(old_path)

    logger.info("CV saved for application %d: %s (%d bytes)", application_id, filename, size)
    return application


@app.get("/applications/{application_id}/cv", tags=["applications"])
def download_cv(
    application_id: int,
    session: Session = Depends(get_session),
) -> FileResponse:
    application = _get_or_404(session, application_id)
    if not application.cv_path:
        raise HTTPException(status_code=404, detail="No CV uploaded for this application")

    full = cv_full_path(application.cv_path)
    if not full.is_file():
        raise HTTPException(status_code=404, detail="CV file missing on disk")

    return FileResponse(
        path=full,
        filename=application.cv_filename or full.name,
        media_type="application/octet-stream",
    )


@app.delete("/applications/{application_id}/cv", status_code=204, tags=["applications"])
def delete_cv(
    application_id: int,
    session: Session = Depends(get_session),
) -> Response:
    application = _get_or_404(session, application_id)
    if not application.cv_path:
        raise HTTPException(status_code=404, detail="No CV uploaded for this application")

    old_path = application.cv_path
    application.cv_path = None
    application.cv_filename = None
    session.add(application)
    session.commit()

    delete_cv_file(old_path)
    return Response(status_code=204)