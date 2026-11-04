from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AnalysisJob, Camera, CrowdEvent, FollowingEvent, GroupEvent, TrackRecord, Video
from ..schemas import JobCreate, crowd_out, following_out, group_out, job_out
from ..services.jobs import manager
from ..services.render import encode_png, heatmap_image, trajectory_image
from ..services.reports import job_pdf
from ..services.settings_service import load_settings

router = APIRouter(prefix="/api/jobs", tags=["analysis"])


def _job(db: Session, job_id: int) -> AnalysisJob:
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.post("")
def create_job(body: JobCreate, db: Session = Depends(get_db)):
    settings = load_settings(db).to_dict()
    settings.update(body.settings or {})
    if body.video_id:
        video = db.get(Video, body.video_id)
        if not video:
            raise HTTPException(404, "Video not found")
        job = AnalysisJob(video_id=video.id, source=video.path, settings=settings)
    elif body.camera_id:
        cam = db.get(Camera, body.camera_id)
        if not cam:
            raise HTTPException(404, "Camera not found")
        running = db.query(AnalysisJob).filter(AnalysisJob.camera_id == cam.id,
                                               AnalysisJob.status.in_(["queued", "running"])).first()
        if running:
            return job_out(running)
        job = AnalysisJob(camera_id=cam.id, source=cam.source_url, is_live=True, settings=settings)
    elif body.source:
        job = AnalysisJob(source=body.source.strip(), is_live=True, settings=settings)
    else:
        raise HTTPException(400, "Provide video_id, camera_id or source")
    db.add(job)
    db.commit()
    manager.submit(job.id)
    return job_out(job)


@router.get("")
def list_jobs(status: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(AnalysisJob)
    if status:
        q = q.filter(AnalysisJob.status.in_(status.split(",")))
    return [job_out(j, brief=True, runtime=manager.runtime(j.id))
            for j in q.order_by(AnalysisJob.id.desc()).limit(limit).all()]


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    return job_out(_job(db, job_id), runtime=manager.runtime(job_id))


@router.post("/{job_id}/stop")
def stop_job(job_id: int, db: Session = Depends(get_db)):
    job = _job(db, job_id)
    if not manager.stop(job_id) and job.status in ("queued", "running"):
        job.status = "stopped"
        db.commit()
    return {"ok": True}


@router.delete("/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = _job(db, job_id)
    if job.status in ("queued", "running"):
        raise HTTPException(409, "Stop the job first")
    files = [job.output_path, job.reference_image] + [e.snapshot_path for e in job.following_events] + \
        [e.snapshot_path for e in job.crowd_events]
    db.delete(job)
    db.commit()
    for f in files:
        if f:
            Path(f).unlink(missing_ok=True)
    return {"ok": True}


@router.get("/{job_id}/live")
async def live_stream(job_id: int, request: Request):
    """MJPEG stream of annotated frames while a job is processing."""
    rt = manager.runtime(job_id)
    if rt is None or rt.done:
        raise HTTPException(404, "Job is not processing")

    def wait_frame(seq: int):
        with rt.cond:
            rt.cond.wait_for(lambda: rt.frame_seq != seq or rt.done, timeout=2.0)
            return rt.jpeg, rt.frame_seq

    async def gen():
        rt.viewers += 1
        seq = -1
        try:
            while not rt.done:
                if await request.is_disconnected():
                    break
                jpeg, new_seq = await asyncio.to_thread(wait_frame, seq)
                if jpeg is None or new_seq == seq:
                    continue
                seq = new_seq
                yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + \
                    str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n"
        finally:
            rt.viewers -= 1

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


@router.get("/{job_id}/video")
def annotated_video(job_id: int, db: Session = Depends(get_db)):
    job = _job(db, job_id)
    if not job.output_path or not Path(job.output_path).exists():
        raise HTTPException(404, "Annotated video not available yet")
    return FileResponse(job.output_path, media_type="video/mp4", filename=f"followsense_job_{job_id}.mp4")


@router.get("/{job_id}/reference.jpg")
def reference_image(job_id: int, db: Session = Depends(get_db)):
    job = _job(db, job_id)
    if not job.reference_image or not Path(job.reference_image).exists():
        raise HTTPException(404, "No reference frame")
    return FileResponse(job.reference_image, media_type="image/jpeg")


@router.get("/{job_id}/heatmap.png")
def heatmap_png(job_id: int, db: Session = Depends(get_db)):
    job = _job(db, job_id)
    if not job.heatmap:
        raise HTTPException(404, "Heatmap available after analysis")
    return Response(encode_png(heatmap_image(job)), media_type="image/png")


@router.get("/{job_id}/trajectories.png")
def trajectories_png(job_id: int, db: Session = Depends(get_db)):
    job = _job(db, job_id)
    tracks = db.query(TrackRecord).filter(TrackRecord.job_id == job_id).all()
    hi = {e.leader_id for e in job.following_events} | {e.follower_id for e in job.following_events}
    return Response(encode_png(trajectory_image(job, tracks, hi)), media_type="image/png")


@router.get("/{job_id}/analytics")
def analytics(job_id: int, db: Session = Depends(get_db)):
    job = _job(db, job_id)
    tracks = db.query(TrackRecord).filter(TrackRecord.job_id == job_id).order_by(TrackRecord.track_id).all()
    speeds = job.speeds or []
    bins = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 99]
    speed_hist = Counter()
    for sp in speeds:
        for lo, hi in zip(bins, bins[1:]):
            if lo <= sp < hi:
                speed_hist[f"{lo}-{hi if hi < 99 else '+'}"] += 1
                break
    groups = db.query(GroupEvent).filter(GroupEvent.job_id == job_id).all()
    size_dist = Counter(g.max_size for g in groups)
    return {
        "job": job_out(job, runtime=manager.runtime(job_id)),
        "width": job.width, "height": job.height,
        "tracks": [{"track_id": t.track_id, "first_seen": t.first_seen, "last_seen": t.last_seen,
                    "avg_speed": t.avg_speed, "total_distance": t.total_distance, "direction": t.direction,
                    "path": t.path} for t in tracks],
        "heatmap": job.heatmap,
        "directions": job.directions or [0] * 8,
        "speed_histogram": [{"bin": k, "count": speed_hist.get(k, 0)}
                            for k in [f"{lo}-{hi if hi < 99 else '+'}" for lo, hi in zip(bins, bins[1:])]],
        "crowd": job.crowd or {},
        "relationships": job.relationships or {},
        "groups": [group_out(g) for g in groups],
        "group_sizes": {str(k): v for k, v in sorted(size_dist.items())},
        "following": [following_out(e) for e in job.following_events],
        "crowd_events": [crowd_out(c) for c in job.crowd_events],
    }


@router.get("/{job_id}/report.pdf")
def report(job_id: int, db: Session = Depends(get_db)):
    job = _job(db, job_id)
    following = db.query(FollowingEvent).filter(FollowingEvent.job_id == job_id) \
        .order_by(FollowingEvent.start_time).all()
    groups = db.query(GroupEvent).filter(GroupEvent.job_id == job_id).order_by(GroupEvent.start_time).all()
    crowd = db.query(CrowdEvent).filter(CrowdEvent.job_id == job_id).order_by(CrowdEvent.start_time).all()
    tracks = db.query(TrackRecord).filter(TrackRecord.job_id == job_id).all()
    pdf = job_pdf(job, following, groups, crowd, tracks)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="followsense_report_job_{job_id}.pdf"'})
