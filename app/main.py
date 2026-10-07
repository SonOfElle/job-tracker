"""Job Application Tracker API."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from sqlalchemy import select, text
from sqlmodel import Session

from app.database import get_session, init_db
from app.models import (
    Application,
    ApplicationCreate,
    ApplicationRead,
    ApplicationStatus,
    ApplicationUpdate,
    StrategyType,
)

logger = logging.getLogger("job_tracker")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    logger.info("Database ready; schema ensured.")
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


@app.delete("/applications/{application_id}", status_code=204, tags=["applications"])
def delete_application(application_id: int, session: Session = Depends(get_session)) -> Response:
    application = _get_or_404(session, application_id)
    session.delete(application)
    session.commit()
    return Response(status_code=204)