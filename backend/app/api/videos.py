from __future__ import annotations

import re
import uuid
from pathlib import Path

import cv2
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import app_config
from ..database import get_db
from ..models import AnalysisJob, Video
from ..schemas import video_out
from ..services.jobs import manager
from ..services.settings_service import load_settings

router = APIRouter(prefix="/api/videos", tags=["videos"])
ALLOWED = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm", ".mpg", ".mpeg"}


def probe(path: Path) -> dict:
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            return {}
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        ok, frame = cap.read()
        h, w = frame.shape[:2] if ok else (int(cap.get(4)), int(cap.get(3)))  # rotation-aware
        return {"fps": round(fps, 3), "frame_count": frames, "width": w, "height": h,
                "duration": round(frames / fps, 2) if fps else 0}
    finally:
        cap.release()


@router.post("")
async def upload_video(file: UploadFile = File(...), analyze: bool = Query(True), db: Session = Depends(get_db)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(400, f"Unsupported file type {ext or '(none)'}")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(file.filename).name)[-80:]
    dest = app_config.upload_dir / f"{uuid.uuid4().hex[:10]}_{safe}"
    size = 0
    with dest.open("wb") as fh:
        while chunk := await file.read(1024 * 1024 * 4):
            fh.write(chunk)
            size += len(chunk)
    meta = probe(dest)
    if not meta:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "The file could not be decoded as a video")
    video = Video(original_name=Path(file.filename).name, path=str(dest), size_bytes=size, **meta)
    db.add(video)
    db.commit()
    job = None
    if analyze:
        job = AnalysisJob(video_id=video.id, source=str(dest), settings=load_settings(db).to_dict())
        db.add(job)
        db.commit()
        manager.submit(job.id)
    return video_out(video, job)


@router.get("")
def list_videos(db: Session = Depends(get_db)):
    videos = db.query(Video).order_by(Video.created_at.desc()).all()
    out = []
    for v in videos:
        latest = max(v.jobs, key=lambda j: j.id) if v.jobs else None
        out.append(video_out(v, latest))
    return out


@router.get("/{video_id}")
def get_video(video_id: int, db: Session = Depends(get_db)):
    v = db.get(Video, video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    d = video_out(v, max(v.jobs, key=lambda j: j.id) if v.jobs else None)
    d["jobs"] = [{"id": j.id, "status": j.status, "created_at": j.created_at, "progress": j.progress}
                 for j in sorted(v.jobs, key=lambda j: -j.id)]
    return d


@router.get("/{video_id}/file")
def video_file(video_id: int, db: Session = Depends(get_db)):
    v = db.get(Video, video_id)
    if not v or not Path(v.path).exists():
        raise HTTPException(404, "Video not found")
    return FileResponse(v.path, filename=v.original_name)


@router.delete("/{video_id}")
def delete_video(video_id: int, db: Session = Depends(get_db)):
    v = db.get(Video, video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    if any(j.status in ("running", "queued") for j in v.jobs):
        raise HTTPException(409, "Stop the running analysis first")
    files = [v.path]
    for j in v.jobs:
        files += [j.output_path, j.reference_image]
        files += [e.snapshot_path for e in j.following_events] + [e.snapshot_path for e in j.crowd_events]
    db.delete(v)
    db.commit()
    for f in files:
        if f:
            Path(f).unlink(missing_ok=True)
    return {"ok": True}
