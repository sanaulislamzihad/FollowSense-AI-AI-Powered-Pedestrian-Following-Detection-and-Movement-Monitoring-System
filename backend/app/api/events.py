from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CrowdEvent, FollowingEvent, GroupEvent, utcnow
from ..schemas import ReviewIn, crowd_out, following_out, group_out
from ..services.reports import crowd_csv, following_csv

router = APIRouter(prefix="/api/events", tags=["events"])


def _following_query(db, job_id, status, min_confidence):
    q = db.query(FollowingEvent)
    if job_id:
        q = q.filter(FollowingEvent.job_id == job_id)
    if status:
        q = q.filter(FollowingEvent.status.in_(status.split(",")))
    if min_confidence:
        q = q.filter(FollowingEvent.confidence >= min_confidence)
    return q.order_by(FollowingEvent.created_at.desc(), FollowingEvent.id.desc())


@router.get("/following")
def list_following(job_id: int | None = None, status: str | None = None, min_confidence: float = 0,
                   limit: int = 200, db: Session = Depends(get_db)):
    return [following_out(e) for e in _following_query(db, job_id, status, min_confidence).limit(limit)]


@router.get("/following/export.csv")
def export_following(job_id: int | None = None, status: str | None = None, min_confidence: float = 0,
                     db: Session = Depends(get_db)):
    data = following_csv(_following_query(db, job_id, status, min_confidence).all())
    name = f"following_events{'_job_' + str(job_id) if job_id else ''}.csv"
    return Response(data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/following/{event_id}")
def get_following(event_id: int, db: Session = Depends(get_db)):
    e = db.get(FollowingEvent, event_id)
    if not e:
        raise HTTPException(404, "Event not found")
    return following_out(e)


@router.patch("/following/{event_id}")
def review_following(event_id: int, body: ReviewIn, db: Session = Depends(get_db)):
    e = db.get(FollowingEvent, event_id)
    if not e:
        raise HTTPException(404, "Event not found")
    if body.status:
        e.status, e.reviewed_at = body.status, utcnow()
    if body.notes is not None:
        e.notes = body.notes
    db.commit()
    return following_out(e)


@router.get("/following/{event_id}/snapshot.jpg")
def following_snapshot(event_id: int, db: Session = Depends(get_db)):
    e = db.get(FollowingEvent, event_id)
    if not e or not e.snapshot_path or not Path(e.snapshot_path).exists():
        raise HTTPException(404, "No snapshot")
    return FileResponse(e.snapshot_path, media_type="image/jpeg")


@router.get("/crowd")
def list_crowd(job_id: int | None = None, status: str | None = None, limit: int = 200,
               db: Session = Depends(get_db)):
    q = db.query(CrowdEvent)
    if job_id:
        q = q.filter(CrowdEvent.job_id == job_id)
    if status:
        q = q.filter(CrowdEvent.status.in_(status.split(",")))
    return [crowd_out(c) for c in q.order_by(CrowdEvent.created_at.desc(), CrowdEvent.id.desc()).limit(limit)]


@router.get("/crowd/export.csv")
def export_crowd(job_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(CrowdEvent)
    if job_id:
        q = q.filter(CrowdEvent.job_id == job_id)
    return Response(crowd_csv(q.order_by(CrowdEvent.id).all()), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="crowd_events.csv"'})


@router.patch("/crowd/{event_id}")
def review_crowd(event_id: int, body: ReviewIn, db: Session = Depends(get_db)):
    c = db.get(CrowdEvent, event_id)
    if not c:
        raise HTTPException(404, "Event not found")
    if body.status:
        c.status = body.status
    db.commit()
    return crowd_out(c)


@router.get("/crowd/{event_id}/snapshot.jpg")
def crowd_snapshot(event_id: int, db: Session = Depends(get_db)):
    c = db.get(CrowdEvent, event_id)
    if not c or not c.snapshot_path or not Path(c.snapshot_path).exists():
        raise HTTPException(404, "No snapshot")
    return FileResponse(c.snapshot_path, media_type="image/jpeg")


@router.get("/groups")
def list_groups(job_id: int | None = None, limit: int = 200, db: Session = Depends(get_db)):
    q = db.query(GroupEvent)
    if job_id:
        q = q.filter(GroupEvent.job_id == job_id)
    return [group_out(g) for g in q.order_by(GroupEvent.id.desc()).limit(limit)]
