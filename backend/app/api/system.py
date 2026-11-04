"""Overview dashboard, cameras and settings endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import DetectionSettings
from ..database import get_db
from ..models import AnalysisJob, Camera, CrowdEvent, FollowingEvent, GroupEvent, Video
from ..schemas import CameraIn, camera_out, crowd_out, following_out, job_out
from ..services.jobs import manager
from ..services.settings_service import load_settings, reset_settings, save_settings

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    completed = db.query(AnalysisJob).filter(AnalysisJob.status.in_(["completed", "stopped"]))
    running = db.query(AnalysisJob).filter(AnalysisJob.status.in_(["running", "queued"])).all()
    active_tracks = 0
    live_people = 0
    for j in running:
        rt = manager.runtime(j.id)
        if rt and rt.status:
            live_people += rt.status.get("count", 0)
            active_tracks += rt.status.get("tracks_total", 0)
    rel_totals: dict[str, int] = {}
    for (rel,) in completed.with_entities(AnalysisJob.relationships).all():
        for k, v in (rel or {}).items():
            rel_totals[k] = rel_totals.get(k, 0) + v
    status_counts = dict(db.query(FollowingEvent.status, func.count()).group_by(FollowingEvent.status).all())
    recent_jobs = db.query(AnalysisJob).order_by(AnalysisJob.id.desc()).limit(6).all()
    return {
        "videos": db.query(Video).count(),
        "cameras": db.query(Camera).count(),
        "jobs_completed": completed.count(),
        "jobs_running": len(running),
        "total_pedestrians": int(completed.with_entities(func.coalesce(func.sum(AnalysisJob.total_pedestrians), 0)).scalar()),
        "active_tracks": active_tracks,
        "live_people": live_people,
        "following_events": db.query(FollowingEvent).count(),
        "following_unreviewed": status_counts.get("new", 0),
        "following_by_status": status_counts,
        "group_events": db.query(GroupEvent).count(),
        "crowd_alerts": db.query(CrowdEvent).count(),
        "peak_crowd": int(db.query(func.coalesce(func.max(AnalysisJob.peak_count), 0)).scalar()),
        "relationships": rel_totals,
        "recent_alerts": [following_out(e) for e in
                          db.query(FollowingEvent).order_by(FollowingEvent.id.desc()).limit(8)],
        "recent_crowd": [crowd_out(c) for c in db.query(CrowdEvent).order_by(CrowdEvent.id.desc()).limit(5)],
        "running_jobs": [job_out(j, brief=True, runtime=manager.runtime(j.id)) for j in running],
        "recent_jobs": [job_out(j, brief=True) for j in recent_jobs],
    }


# --------------------------------------------------------------------- cameras
@router.get("/cameras")
def list_cameras(db: Session = Depends(get_db)):
    out = []
    for c in db.query(Camera).order_by(Camera.id).all():
        live = next((j for j in c.jobs if j.status in ("queued", "running")), None)
        out.append(camera_out(c, live))
    return out


@router.post("/cameras")
def create_camera(body: CameraIn, db: Session = Depends(get_db)):
    cam = Camera(**body.model_dump())
    db.add(cam)
    db.commit()
    return camera_out(cam)


@router.put("/cameras/{camera_id}")
def update_camera(camera_id: int, body: CameraIn, db: Session = Depends(get_db)):
    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Camera not found")
    for k, v in body.model_dump().items():
        setattr(cam, k, v)
    db.commit()
    return camera_out(cam)


@router.delete("/cameras/{camera_id}")
def delete_camera(camera_id: int, db: Session = Depends(get_db)):
    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Camera not found")
    for j in cam.jobs:
        if j.status in ("queued", "running"):
            manager.stop(j.id)
    db.delete(cam)
    db.commit()
    return {"ok": True}


# -------------------------------------------------------------------- settings
@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    return {"values": load_settings(db).to_dict(), "defaults": DetectionSettings().to_dict()}


@router.put("/settings")
def put_settings(values: dict, db: Session = Depends(get_db)):
    return {"values": save_settings(db, values).to_dict(), "defaults": DetectionSettings().to_dict()}


@router.post("/settings/reset")
def post_reset(db: Session = Depends(get_db)):
    return {"values": reset_settings(db).to_dict(), "defaults": DetectionSettings().to_dict()}
